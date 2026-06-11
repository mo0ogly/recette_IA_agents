# Build Pipeline Rust -- Reference partagee APEX v6.0

> Mandatory pipeline for every Rust file created or modified.
> Integrates: rust-best-practices skill, error-handling-patterns skill, clippy + test gates.
> Replaces the Go pipeline in APEX (this project imposes Rust as the backend language).

---

## Mandatory skills (invoke BEFORE writing Rust)

| Skill | When | Role in pipeline |
|-------|------|------------------|
| `rust-best-practices` | BEFORE writing or refactoring any `.rs` | Idiomatic borrowing/ownership, Result handling, clippy lints, perf, tests (Apollo handbook, 9 chapters) |
| `error-handling-patterns` | Any fallible path (I/O, parse, network, FFI) | Result vs panic, `thiserror`/`anyhow` selection, error hierarchies, retry/circuit-breaker, graceful degradation |

These two skills are NON-OPTIONAL. APEX MUST load `rust-best-practices` in Phase 2 (THINK)
and `error-handling-patterns` whenever a subtask touches a fallible boundary.

---

## Sequential pipeline (each `.rs` file)

```
EDIT/WRITE .rs
    |
    v
STEP 1: cargo build
    |-- cargo build 2>&1 (workspace-aware: -p <crate> if multi-crate)
    |-- FAIL -> STOP, fix, re-build
    |-- NEVER bypass with rustc direct (loses workspace + feature resolution)
    |
    v
STEP 2: cargo fmt
    |-- cargo fmt --all -- --check  (0 diff = PASS)
    |-- FAIL -> run `cargo fmt --all`, re-check
    |
    v
STEP 3: cargo clippy (gate = -D warnings)
    |-- cargo clippy --all-targets --all-features -- -D warnings 2>&1
    |-- 0 warnings = PASS (clippy warnings are BLOCKING, per rust-best-practices chapter_02)
    |-- FAIL -> STOP, fix. NEVER #[allow(...)] without a `// reason:` comment
    |
    v
STEP 4: test-first (cargo test)
    |-- Create #[cfg(test)] mod tests in same file OR tests/{name}.rs
    |-- Minimum: 1 nominal + 1 error + 1 edge case
    |-- Naming + one-assertion-per-test per rust-best-practices chapter_05
    |-- cargo test 2>&1 (or cargo nextest run if available)
    |-- PASS = continue, FAIL = fix the CODE (not the test)
    |
    v
STEP 5: Error-handling + convention check
    |-- No unwrap()/expect() on fallible paths in non-test code (use ? + typed errors)
    |-- No panic! in library code (reserve for unrecoverable invariants)
    |-- Errors typed via thiserror (libs) or anyhow (binaries) per error-handling-patterns
    |-- No println!/eprintln! for logging (use the tracing/log facade)
    |-- No hardcoded secrets/URLs
    |
    v
GATE PASSED -> file ready for RECETTE phase
```

---

## Rust construction rules

### Borrowing & ownership
- Prefer `&T` over `.clone()` unless ownership transfer is required (chapter_01, chapter_03).
- Derive `Copy` only for small, semantically-copyable types.
- Return `impl Iterator` instead of allocating intermediate `Vec` when possible.

### Error handling (error-handling-patterns + chapter_04)

```rust
// CORRECT: typed error, propagated with ?
#[derive(Debug, thiserror::Error)]
pub enum ParseError {
    #[error("invalid header: {0}")]
    InvalidHeader(String),
    #[error(transparent)]
    Io(#[from] std::io::Error),
}

fn parse(input: &str) -> Result<Record, ParseError> {
    let header = input.lines().next().ok_or_else(|| ParseError::InvalidHeader("empty".into()))?;
    // ...
}

// FORBIDDEN in non-test code
let v = something().unwrap();           // panics, no context
let v = something().expect("bad");      // panics, loses error type
```

- `?` for propagation, never `unwrap()`/`expect()` on user/IO-driven values.
- `anyhow::Context::context()` to add context in binaries; typed `thiserror` enums in libraries.
- Graceful degradation: timeouts, retries with backoff, circuit breaker for external calls
  (see error-handling-patterns for the concrete patterns).

### Logging
```rust
// CORRECT
tracing::info!(component = "PARSER", action = "INIT", "parser ready");

// FORBIDDEN
println!("processing: {}", id);
eprintln!("error: {}", e);
```

### Tests (test-first patterns, chapter_05)
```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_returns_record_on_valid_input() {
        let out = parse("HDR\nbody").expect("valid input parses");
        assert_eq!(out.kind, RecordKind::Header);
    }

    #[test]
    fn parse_errors_on_empty_input() {
        assert!(matches!(parse(""), Err(ParseError::InvalidHeader(_))));
    }
}
```
- One logical assertion per test, descriptive `fn` names (`<unit>_<expected>_<condition>`).
- `expect()` is allowed INSIDE tests (failure message is the assertion).

---

## Debug Rust (methodology integrated)

When build/clippy/test fails during the pipeline:

### Phase 1: REPRODUCE
```bash
cargo build 2>&1 | head -30
cargo clippy --all-targets -- -D warnings 2>&1 | head -30
```

### Phase 2: ISOLATE
```bash
git diff --name-only HEAD~5 -- '*.rs'   # 80% of bugs = recent code
cargo build 2>&1 | grep -E '^error' | head
RUST_BACKTRACE=1 cargo test <failing_test> -- --nocapture
```

### Phase 3: FIX
- Minimal fix (fewest files).
- Fix the ROOT CAUSE, not the symptom.
- Borrow-checker error: fix the lifetime/ownership model, do NOT sprinkle `.clone()` to silence it.

### Phase 4: VALIDATE
- Reproduce original scenario (bug gone).
- Regression: existing tests pass (`cargo test`).
- Clean diff: no `dbg!`, no leftover `println!`, no commented `#[allow]`.

### Replanning
- 2 consecutive failures -> invoke `/replan`.
- NEVER improvise: root cause identified BEFORE fix.
- Fallback: `git bisect` -> `RUST_BACKTRACE=full` -> minimal failing unit test.

---

## Go -> Rust tool equivalence (security domain mapping)

Used by PDCA security scoring (the Go pipeline scored security via gosec + govulncheck
inside `/go-recette`; there is no `/rust-recette`, so security is scored from these tools).

| Go tool | Purpose | Rust equivalent | Gate |
|---------|---------|-----------------|------|
| `go build` | compile | `cargo build` | exit 0 |
| `go vet` | static correctness | `cargo clippy --all-targets -- -D warnings` | 0 warnings |
| `gofmt` | formatting | `cargo fmt --all -- --check` | 0 diff |
| `gosec` | SAST / security lints | `cargo clippy` security lints + `cargo geiger` (unsafe surface) + `cargo deny check` | 0 HIGH |
| `govulncheck` | vulnerable dependencies | `cargo audit` (RUSTSEC advisories) / `cargo deny check advisories` | 0 unpatched HIGH |
| `go test` | tests | `cargo test` (or `cargo nextest run`) | green |

**Security gate commands** (run at workspace root; tools optional but recommended -- WARN if absent):
```bash
cargo clippy --all-targets --all-features -- -D warnings    # correctness + security lints
cargo audit                                                 # RUSTSEC vulnerable deps (cargo install cargo-audit)
cargo deny check advisories bans licenses sources           # supply-chain (cargo install cargo-deny)
cargo geiger                                                 # unsafe code surface (cargo install cargo-geiger)
```

**Security score /20** (PDCA security domain): start at 20, subtract per finding ->
- RUSTSEC HIGH/CRITICAL unpatched advisory: -6 each
- clippy security/correctness lint (`-D warnings` failure): -4 each
- `unsafe` block without `// SAFETY:` justification (cargo geiger): -3 each
- `cargo deny` ban/license/source violation: -2 each
Floor at 0. Zero RUSTSEC HIGH/CRITICAL is a hard gate (CRITICAL FAIL if present).

---

## Rust pipeline score /5

| Criterion | Points | When 1 point |
|-----------|--------|--------------|
| cargo build passes | /1 | exit 0 |
| cargo fmt --check clean | /1 | 0 diff |
| cargo clippy -D warnings | /1 | 0 warnings |
| test-first (cargo test green) | /1 | exit 0, >=1 nominal + 1 error + 1 edge |
| Conventions (typed errors, no unwrap on fallible, tracing not println) | /1 | 0 violation |
