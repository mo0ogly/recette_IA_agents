# agentrail_recette

Static recette scorer for AgentRail (Railgun) Rust code. The Rust counterpart of
the Go `lia_recette` CLI and the executable backend of the `/rust-recette`
command.

It automates the pattern-based blocs (A conventions, B OWASP, C arch/perf,
F invariants I1-I6), orchestrates the cargo static-analysis bloc (D: clippy,
audit, fmt, deny, geiger), and emits a scored report plus a CI exit code.

## Build

```bash
cargo build --release        # from this directory
# binary: target/release/agentrail_recette
```

Audit toolchain (clippy, cargo-audit, cargo-deny, cargo-geiger) is installed by
`scripts/install_rust_audit.sh` at the repo root. A missing tool marks its bloc
`N/A` (never a fabricated result).

## Usage

```bash
agentrail_recette <file|crate-dir>            # text report
agentrail_recette --format json <crate>       # JSON (for apex / audit-pdca)
agentrail_recette --skip-tools <crate>        # blocs A/B/C/F only (fast, no cargo)
agentrail_recette --min-score 39 <crate>      # exit 0 iff gate passes
agentrail_recette --manifest-dir <dir> <crate># override cargo working dir
```

## Scoring

| Bloc | Max | Source |
|------|-----|--------|
| A conventions | 10 | patterns + Cargo.lock check |
| B OWASP | 10 | patterns |
| C arch/perf | 10 | patterns + tests-present |
| D static | 5 | cargo clippy/audit/fmt/deny/geiger |
| E R17 contract gate | 4 | manual (N/A in v1) |
| F invariants I1-I6 | 5 | patterns (I1, I4) + manual |

`N/A` checks are excluded and the bloc is renormalized; the global score is
reported both raw (`/global_max`) and normalized (`/44`). Any critical-severity
failure, any bloc E failure, or any bloc F violation forces a blocking verdict
regardless of score.

## Limitations (v1)

- Pattern checks are line-grep based: they catch the common shapes and a few
  carry a "verify manually" note (e.g. B5 path traversal, B6 error disclosure).
- Semantic checks (auth/identity, async cleanup, control-plane mediation,
  approval blocking, R17 contract gate) are surfaced as `N/A` for human review
  rather than guessed.
- A linter scanning its own rule source (`src/patterns.rs`) will match its own
  regex literals; run with `--skip-tools src/` only to inspect, not to gate the
  tool itself.
