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
