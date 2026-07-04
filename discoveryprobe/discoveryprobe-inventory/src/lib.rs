//! Agent inventory: identifies AI agents from source (passport + code heuristics),
//! cross-checks declared vs observed behaviour, and maps multi-agent communication.
//!
//! Failure mode (fail-safe): when no runtime capture is provided, conformity is
//! `NotObserved` -- never `Conform` by default.

pub mod correlate;
pub mod graph;
pub mod manifest;
pub mod report;
pub mod scan;

/// Shared path helpers for the crate's unit tests (corpus + fixture trees).
#[cfg(test)]
pub(crate) mod test_support {
    use std::path::PathBuf;

    /// Resolves a path under the repo `corpus/` directory. The crate lives at
    /// `discoveryprobe/discoveryprobe-inventory/`, so corpus is two levels up.
    pub(crate) fn corpus_path(rel: &str) -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../corpus")
            .join(rel)
    }

    /// Resolves a committed fixture tree under `tests/fixtures/<name>`.
    pub(crate) fn fixture_path(name: &str) -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("tests/fixtures")
            .join(name)
    }
}
