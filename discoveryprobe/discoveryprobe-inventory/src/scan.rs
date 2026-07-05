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
//!
//! Unlike `adapters.py` which uses early-return precedence between heuristics (temporal wins over openapi wins over github), this scan unions evidence from ALL heuristics: a tree with both temporalio code and github SDK imports emits evidence from both. Detection yes/no parity with the oracle holds for the corpus; consumers must not assume first-match evidence.

use crate::manifest::{Passport, PassportError, KNOWN_GIT_ACTIONS};
use crate::model::Attestation;
use agent_passport::{
    verify, Passport as SignedPassport, Timestamp, TrustStore, UntrustReason, Verdict,
};
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
///
/// Kind-tagged JSON like every bridge-crossing enum (uniform style, see the
/// `model` module header): each value is an object with a `"kind"` key.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum PassportStatus {
    /// A valid passport was found and parsed.
    Present {
        /// The parsed passport.
        passport: Passport,
    },
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

/// One agent located by the scan: the tree root, its manifest status, and its
/// signed-credential attestation.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ScannedAgent {
    /// Scanned tree root (display path as given to the scan, deterministic).
    pub root: String,
    /// Manifest situation of the tree (`.inspect_ia_agents/manifest.json`).
    pub passport: PassportStatus,
    /// Signed-credential situation of the tree
    /// (`.inspect_ia_agents/passport.json`) -- a SEPARATE axis from `passport`.
    /// Set to [`Attestation::Unsigned`] when scanned without a keyring
    /// (`scan_tree`), or resolved against an injected keyring + clock by
    /// [`scan_tree_attested`].
    pub attestation: Attestation,
}

/// Scans one source tree for an agent WITHOUT a keyring: the manifest axis is
/// resolved as usual, and the signed-credential `attestation` is computed with
/// no trust anchors and no clock (`scan_tree_attested(root, None, None)`), so a
/// present `passport.json` is the fail-safe [`Attestation::Untrusted`] with
/// [`UntrustReason::UnknownKeyId`] -- never trusted without a keyring.
///
/// Returns at most one `ScannedAgent`: the tree either declares a manifest
/// (present/invalid) or shows agent-code evidence (absent manifest = shadow
/// agent); with neither, the result is empty -- never an agent claim without
/// proof. A tree that carries ONLY a `passport.json` (no manifest, no code) is
/// therefore not detected here; the attestation axis surfaces on a tree already
/// detected on the manifest/code axis.
pub fn scan_tree(root: &Path) -> Result<Vec<ScannedAgent>, ScanError> {
    scan_tree_attested(root, None, None)
}

/// Scans one source tree, resolving the signed-credential attestation against an
/// injected keyring (`trust`) and clock (`now`). Both are OPTIONAL: when either
/// is absent, a present `passport.json` is the fail-safe
/// [`Attestation::Untrusted`] ([`UntrustReason::UnknownKeyId`]) -- the scan
/// never claims [`Attestation::Trusted`] without an injected keyring AND clock.
/// When both are present, the passport is verified via the pure `agent-passport`
/// [`verify`] (declared scope is `None` here -- see [`read_attestation`]).
///
/// I4: `now` is an INJECTED input; the wall clock is never read.
pub fn scan_tree_attested(
    root: &Path,
    trust: Option<&TrustStore>,
    now: Option<&Timestamp>,
) -> Result<Vec<ScannedAgent>, ScanError> {
    let root_display = root.display().to_string();
    // The attestation axis is per-tree (same root) -- compute it once.
    let attestation = read_attestation(root, trust, now);
    let manifest_path = root.join(".inspect_ia_agents").join("manifest.json");
    if manifest_path.exists() {
        let raw = read_file(&manifest_path)?;
        let passport = match Passport::parse(&raw) {
            Ok(p) => PassportStatus::Present { passport: p },
            Err(e) => PassportStatus::Invalid {
                errors: passport_error_strings(&e),
            },
        };
        return Ok(vec![ScannedAgent {
            root: root_display,
            passport,
            attestation,
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
        attestation,
    }])
}

/// Reads `<root>/.inspect_ia_agents/passport.json` and resolves it to an
/// [`Attestation`], fail-safe (never panics, never errors the scan):
///
/// - no file -> [`Attestation::Unsigned`];
/// - present but unreadable or unparseable -> [`Attestation::Malformed`]
///   (the signed-axis parallel of [`PassportStatus::Invalid`]);
/// - parsed, with BOTH `trust` and `now` -> the pure [`verify`] verdict, mapped
///   to [`Attestation::Trusted`] / [`Attestation::Untrusted`];
/// - parsed, but `trust` OR `now` absent -> fail-safe
///   [`Attestation::Untrusted`] with [`UntrustReason::UnknownKeyId`]: without an
///   injected keyring AND clock the scan cannot establish trust, so it never
///   claims trusted.
///
/// The declared scope is `None`: the scan attestation covers
/// signature + expiry + delegation, NOT scope overreach. The manifest-vs-passport
/// scope cross-check is exercised by the standalone `passport verify --declared`
/// (and the corpus subject), out of scope for the inventory scan.
fn read_attestation(
    root: &Path,
    trust: Option<&TrustStore>,
    now: Option<&Timestamp>,
) -> Attestation {
    let passport_path = root.join(".inspect_ia_agents").join("passport.json");
    if !passport_path.exists() {
        return Attestation::Unsigned;
    }
    let raw = match std::fs::read(&passport_path) {
        Ok(bytes) => bytes,
        Err(e) => {
            return Attestation::Malformed {
                message: format!("cannot read passport.json: {e}"),
            }
        }
    };
    let passport = match SignedPassport::from_json(&raw) {
        Ok(p) => p,
        Err(e) => {
            return Attestation::Malformed {
                message: e.to_string(),
            }
        }
    };
    match (trust, now) {
        // Real verification only with an injected keyring AND clock.
        (Some(trust), Some(now)) => attestation_from_verdict(verify(&passport, trust, now, None)),
        // Fail-safe: no keyring/clock -> cannot establish trust -> unknown key.
        _ => Attestation::Untrusted {
            reasons: vec![UntrustReason::UnknownKeyId],
        },
    }
}

/// Maps a pure [`verify`] [`Verdict`] to an inventory [`Attestation`].
fn attestation_from_verdict(verdict: Verdict) -> Attestation {
    match verdict {
        Verdict::Trusted => Attestation::Trusted,
        Verdict::Untrusted { reasons } => Attestation::Untrusted { reasons },
    }
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
                // Falls back only on ABSENT key, not JSON null -- Python's `or` also falls back on null/empty.
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
        assert!(matches!(found[0].passport, PassportStatus::Present { .. }));
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
        assert_eq!(
            found.len(),
            1,
            "invalid-passport fixture must produce exactly one result"
        );
        assert!(matches!(found[0].passport, PassportStatus::Invalid { .. }));
    }

    // --- attestation axis (signed passport.json) --------------------------
    //
    // These build throwaway temp trees: a shadow agent (`agent/bot.py` with a
    // github import) so the tree is DETECTED on the manifest/code axis, plus an
    // optional `passport.json` to exercise the ORTHOGONAL attestation axis.

    /// Creates a fresh temp tree containing an `agent/bot.py` that imports the
    /// github SDK (so the tree scans as a shadow agent) and returns its path.
    fn shadow_tree(tag: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "discoveryprobe-scan-attest-{tag}-{}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(dir.join("agent")).expect("create tree");
        std::fs::write(dir.join("agent").join("bot.py"), "import github\n").expect("write bot");
        dir
    }

    /// A minimal, parseable (but unsigned-in-practice) `passport.json` body:
    /// every required field is present, so `SignedPassport::from_json` succeeds;
    /// the signature is a placeholder (verification is exercised end-to-end via
    /// the CLI integration tests with a real key).
    const MINIMAL_PASSPORT: &str = r#"{"id":"a","tenant":"t","delegation":["human:alice"],"scope":["read_repo"],"exp":"2999-01-01T00:00:00Z","signature":"00","key_id":"k"}"#;

    #[test]
    fn no_passport_json_is_attestation_unsigned() {
        let tree = shadow_tree("unsigned");
        let found = scan_tree(&tree).expect("scan");
        assert_eq!(found.len(), 1);
        // Manifest axis: shadow (Absent). Attestation axis: Unsigned. Orthogonal.
        assert!(matches!(found[0].passport, PassportStatus::Absent { .. }));
        assert_eq!(found[0].attestation, Attestation::Unsigned);
        let _ = std::fs::remove_dir_all(&tree);
    }

    #[test]
    fn present_passport_without_keyring_is_untrusted_unknown_key() {
        let tree = shadow_tree("nokeyring");
        std::fs::create_dir_all(tree.join(".inspect_ia_agents")).expect("mk .inspect_ia_agents");
        std::fs::write(
            tree.join(".inspect_ia_agents").join("passport.json"),
            MINIMAL_PASSPORT,
        )
        .expect("write passport");
        // scan_tree passes no trust/no clock: fail-safe unknown key.
        let found = scan_tree(&tree).expect("scan");
        assert_eq!(found.len(), 1);
        assert_eq!(
            found[0].attestation,
            Attestation::Untrusted {
                reasons: vec![UntrustReason::UnknownKeyId],
            }
        );
        let _ = std::fs::remove_dir_all(&tree);
    }

    #[test]
    fn corrupt_passport_json_is_attestation_malformed() {
        let tree = shadow_tree("malformed");
        std::fs::create_dir_all(tree.join(".inspect_ia_agents")).expect("mk .inspect_ia_agents");
        std::fs::write(
            tree.join(".inspect_ia_agents").join("passport.json"),
            "not a passport at all",
        )
        .expect("write corrupt");
        let found = scan_tree(&tree).expect("scan");
        assert_eq!(found.len(), 1);
        assert!(
            matches!(found[0].attestation, Attestation::Malformed { .. }),
            "expected Malformed, got {:?}",
            found[0].attestation
        );
        let _ = std::fs::remove_dir_all(&tree);
    }
}
