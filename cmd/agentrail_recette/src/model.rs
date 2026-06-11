//! Core data model: checks, verdicts, findings, and their serialized form.

use serde::Serialize;

/// Outcome of a single check.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub enum Verdict {
    /// The check passed.
    #[serde(rename = "PASS")]
    Pass,
    /// The check failed (one or more findings).
    #[serde(rename = "FAIL")]
    Fail,
    /// The check is not applicable or its tool is unavailable.
    #[serde(rename = "N/A")]
    Na,
}

/// Severity tier of a check, mirroring the /rust-recette command.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Severity {
    /// Blocks the merge.
    Critical,
    /// Must be fixed before merge.
    Major,
    /// Fix before production.
    Minor,
}

/// A single location where a check matched.
#[derive(Debug, Clone, Serialize)]
pub struct Finding {
    /// Relative path of the offending file.
    pub file: String,
    /// 1-based line number.
    pub line: usize,
    /// Trimmed, length-capped excerpt of the matching line.
    pub excerpt: String,
}

/// Result of evaluating one check across the scanned files.
#[derive(Debug, Clone, Serialize)]
pub struct CheckResult {
    /// Stable check identifier (e.g. `A1`, `D2`, `F4`).
    pub id: &'static str,
    /// Human-readable check name.
    pub name: &'static str,
    /// Bloc letter (`A`..`F`).
    pub bloc: char,
    /// Severity tier.
    pub severity: Severity,
    /// Outcome.
    pub verdict: Verdict,
    /// Findings (empty unless `verdict == Fail`).
    pub findings: Vec<Finding>,
    /// Optional note (rationale, tool name, manual-review hint).
    pub note: Option<String>,
}

impl CheckResult {
    /// Build a passing result.
    pub fn pass(id: &'static str, name: &'static str, bloc: char, severity: Severity) -> Self {
        Self {
            id,
            name,
            bloc,
            severity,
            verdict: Verdict::Pass,
            findings: Vec::new(),
            note: None,
        }
    }

    /// Build a failing result from its findings.
    pub fn fail(
        id: &'static str,
        name: &'static str,
        bloc: char,
        severity: Severity,
        findings: Vec<Finding>,
    ) -> Self {
        Self {
            id,
            name,
            bloc,
            severity,
            verdict: Verdict::Fail,
            findings,
            note: None,
        }
    }

    /// Build a not-applicable result with an explanatory note.
    pub fn na(
        id: &'static str,
        name: &'static str,
        bloc: char,
        severity: Severity,
        note: impl Into<String>,
    ) -> Self {
        Self {
            id,
            name,
            bloc,
            severity,
            verdict: Verdict::Na,
            findings: Vec::new(),
            note: Some(note.into()),
        }
    }

    /// Attach a note, builder-style.
    #[must_use]
    pub fn with_note(mut self, note: impl Into<String>) -> Self {
        self.note = Some(note.into());
        self
    }

    /// True when this is a critical check that failed (forces a blocking verdict).
    pub fn is_critical_fail(&self) -> bool {
        self.verdict == Verdict::Fail && self.severity == Severity::Critical
    }
}
