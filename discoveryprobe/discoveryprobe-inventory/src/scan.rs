//! Source-tree scan: locates agents via passports and code heuristics.
//!
//! Detection precedence mirrors the recette reference oracle
//! (`recette/adapters.py::ReferenceSourceScanAdapter._analyze`):
//!
//! 1. `.inspect_ia_agents/manifest.json` at the tree root -> `Passport::parse`
//!    -> `Present` (valid) or `Invalid` (the parse errors, auditor-facing).
//! 2. else agent-code heuristics (the shadow-agent path): github SDK imports
//!    under `agent/` (`_has_github_agent_code`), temporalio workflow/activity
//!    definitions in any `*.py` (`_has_temporal_agent_code`), or a root
//!    `openapi.json` whose operations carry canonical actions (`_from_openapi`).
//!    Every hit is ONE evidence string (relative path + needle) an auditor can
//!    reproduce; evidence is sorted and deduplicated (I4).
//! 3. no passport and no evidence -> empty result: the scan NEVER claims an
//!    agent without proof (true negative, R13).
//!
//! Determinism (I4): files are walked in sorted order and unreadable
//! (e.g. non-UTF8) files are skipped without failing the scan.
//!
//! Failure mode (fail-safe): an unreadable directory, or a manifest that
//! exists but cannot be read, is a `ScanError` -- never a silent "no agent".

use crate::manifest::{Passport, PassportError, KNOWN_GIT_ACTIONS};
use serde::{Deserialize, Serialize};
use std::fmt;
use std::path::{Path, PathBuf};

/// Error raised when the tree itself cannot be scanned.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ScanError {
    /// Reading a directory or file failed; carries the path and the OS error.
    Io {
        /// The path that failed to read.
        path: String,
        /// The underlying error message.
        message: String,
    },
}

impl fmt::Display for ScanError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ScanError::Io { path, message } => write!(f, "cannot read {path}: {message}"),
        }
    }
}

impl std::error::Error for ScanError {}

/// Passport situation of a scanned tree: declared, missing, or broken.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum PassportStatus {
    /// A valid passport was found and parsed.
    Present(Passport),
    /// No passport, but agent code was found: the shadow-agent case. Each
    /// evidence string is `relative/path: needle`, reproducible by an auditor.
    Absent {
        /// Sorted, deduplicated evidence strings (relative path + needle).
        evidence: Vec<String>,
    },
    /// A passport file exists but does not parse/validate.
    Invalid {
        /// The parse/validation error strings (auditor-facing).
        errors: Vec<String>,
    },
}

/// One agent located by the scan: the tree root plus its passport status.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ScannedAgent {
    /// Scanned tree root (display path as given to the scan, deterministic).
    pub root: String,
    /// Passport situation of the tree.
    pub passport: PassportStatus,
}

/// Scans one source tree for an agent. Returns at most one `ScannedAgent`:
/// the tree either declares a passport (present/invalid) or shows agent-code
/// evidence (absent passport = shadow agent); with neither, the result is
/// empty -- never an agent claim without proof.
pub fn scan_tree(root: &Path) -> Result<Vec<ScannedAgent>, ScanError> {
    let root_display = root.display().to_string();
    let manifest_path = root.join(".inspect_ia_agents").join("manifest.json");
    if manifest_path.exists() {
        let raw = read_file(&manifest_path)?;
        let passport = match Passport::parse(&raw) {
            Ok(p) => PassportStatus::Present(p),
            Err(e) => PassportStatus::Invalid {
                errors: passport_error_strings(&e),
            },
        };
        return Ok(vec![ScannedAgent {
            root: root_display,
            passport,
        }]);
    }
    let mut evidence: Vec<String> = Vec::new();
    evidence.extend(github_code_evidence(root)?);
    evidence.extend(temporal_code_evidence(root)?);
    evidence.extend(openapi_evidence(root)?);
    evidence.sort();
    evidence.dedup();
    if evidence.is_empty() {
        return Ok(Vec::new()); // true negative: no claim without proof.
    }
    Ok(vec![ScannedAgent {
        root: root_display,
        passport: PassportStatus::Absent { evidence },
    }])
}

/// Flattens a `PassportError` into auditor-facing strings: one string for a
/// JSON syntax error, one per rejected shape for a shape mismatch.
fn passport_error_strings(error: &PassportError) -> Vec<String> {
    match error {
        PassportError::InvalidJson(e) => vec![format!("invalid JSON: {e}")],
        PassportError::ShapeMismatch { repo, unified } => vec![
            format!("repo shape: {repo}"),
            format!("unified shape: {unified}"),
        ],
    }
}

/// Reads a file to a string, mapping the I/O error to `ScanError`.
fn read_file(path: &Path) -> Result<String, ScanError> {
    std::fs::read_to_string(path).map_err(|e| ScanError::Io {
        path: path.display().to_string(),
        message: e.to_string(),
    })
}

/// Mirrors `ReferenceSourceScanAdapter._has_github_agent_code`: `*.py` files
/// under an `agent/` directory importing the `github` SDK. One evidence
/// string per (file, needle) hit.
fn github_code_evidence(root: &Path) -> Result<Vec<String>, ScanError> {
    let agent_dir = root.join("agent");
    if !agent_dir.is_dir() {
        return Ok(Vec::new());
    }
    let mut evidence = Vec::new();
    for py in py_files(&agent_dir)? {
        // Non-UTF8 or unreadable file: skip it, never fail the scan.
        let Ok(text) = std::fs::read_to_string(&py) else {
            continue;
        };
        for needle in ["import github", "from github import"] {
            if text.contains(needle) {
                evidence.push(format!("{}: {}", relative_display(root, &py), needle));
            }
        }
    }
    Ok(evidence)
}

/// Mirrors `ReferenceSourceScanAdapter._has_temporal_agent_code`: any `*.py`
/// in the tree containing `temporalio` AND a workflow/activity definition
/// decorator. One evidence string per (file, decorator) hit.
fn temporal_code_evidence(root: &Path) -> Result<Vec<String>, ScanError> {
    let mut evidence = Vec::new();
    for py in py_files(root)? {
        let Ok(text) = std::fs::read_to_string(&py) else {
            continue;
        };
        if !text.contains("temporalio") {
            continue;
        }
        for needle in ["@activity.defn", "@workflow.defn"] {
            if text.contains(needle) {
                evidence.push(format!(
                    "{}: temporalio + {}",
                    relative_display(root, &py),
                    needle
                ));
            }
        }
    }
    Ok(evidence)
}

/// Mirrors `ReferenceSourceScanAdapter._from_openapi`: a root `openapi.json`
/// whose operations carry an `operationId` or `x-inspect_ia_agents-action` in the
/// canonical git action vocabulary (`KNOWN_GIT_ACTIONS`, single source).
fn openapi_evidence(root: &Path) -> Result<Vec<String>, ScanError> {
    let spec_path = root.join("openapi.json");
    if !spec_path.exists() {
        return Ok(Vec::new());
    }
    let raw = read_file(&spec_path)?;
    // A root openapi.json that is not JSON is not agent evidence; only the
    // passport path treats a broken file as an explicit error state.
    let Ok(spec) = serde_json::from_str::<serde_json::Value>(&raw) else {
        return Ok(Vec::new());
    };
    let Some(paths) = spec.get("paths").and_then(|p| p.as_object()) else {
        return Ok(Vec::new());
    };
    let mut evidence = Vec::new();
    for operations in paths.values() {
        let Some(operations) = operations.as_object() else {
            continue;
        };
        for op in operations.values() {
            let Some(op) = op.as_object() else {
                continue;
            };
            let action = op
                .get("operationId")
                .or_else(|| op.get("x-inspect_ia_agents-action"))
                .and_then(|a| a.as_str());
            if let Some(action) = action {
                if KNOWN_GIT_ACTIONS.contains(&action) {
                    evidence.push(format!("openapi.json: operation '{action}'"));
                }
            }
        }
    }
    Ok(evidence)
}

/// Recursively collects `*.py` files under `dir`, in sorted order (I4).
fn py_files(dir: &Path) -> Result<Vec<PathBuf>, ScanError> {
    let mut files = Vec::new();
    collect_py_files(dir, &mut files)?;
    files.sort();
    Ok(files)
}

/// Depth-first collection helper for `py_files`. A directory read error is
/// a `ScanError` (fail-safe: never silently report "no agent code").
fn collect_py_files(dir: &Path, out: &mut Vec<PathBuf>) -> Result<(), ScanError> {
    let entries = std::fs::read_dir(dir).map_err(|e| ScanError::Io {
        path: dir.display().to_string(),
        message: e.to_string(),
    })?;
    for entry in entries {
        let entry = entry.map_err(|e| ScanError::Io {
            path: dir.display().to_string(),
            message: e.to_string(),
        })?;
        let path = entry.path();
        if path.is_dir() {
            collect_py_files(&path, out)?;
        } else if path.extension().and_then(|e| e.to_str()) == Some("py") {
            out.push(path);
        }
    }
    Ok(())
}

/// Displays `path` relative to `root` (evidence strings must be reproducible
/// regardless of the absolute scan location).
fn relative_display(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .display()
        .to_string()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::test_support::{corpus_path, fixture_path};

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
}
