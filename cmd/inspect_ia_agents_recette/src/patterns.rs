//! Pattern-based checks for blocs A, B, C and F, plus structural and
//! manual-review placeholders. Each automated check is "target zero": any match
//! is a finding and fails the check.

use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use regex::Regex;

use crate::model::{CheckResult, Finding, Severity};
use crate::scan;

/// A single "target zero" pattern check.
struct PatternCheck {
    id: &'static str,
    name: &'static str,
    bloc: char,
    severity: Severity,
    regex: Regex,
    /// When true, matches inside `#[cfg(test)]` blocks / test files are ignored.
    exclude_test: bool,
    /// Lines containing any of these markers are exempt (e.g. `// SAFETY:`).
    allow_markers: &'static [&'static str],
    note: Option<&'static str>,
}

/// One row of the pattern-check table before regex compilation.
/// Tuple fields: id, name, bloc, severity, regex source, exclude_test,
/// allow_markers, optional note.
type RawCheck = (
    &'static str,
    &'static str,
    char,
    Severity,
    &'static str,
    bool,
    &'static [&'static str],
    Option<&'static str>,
);

/// Compile the pattern-check table. Returns an error only on an invalid regex
/// (a programming error caught by the unit test below).
fn build() -> Result<Vec<PatternCheck>> {
    let raw: &[RawCheck] = &[
        (
            "A1",
            "tracing only (no println/dbg)",
            'A',
            Severity::Critical,
            r"\b(println!|eprintln!|print!|dbg!)",
            true,
            &[],
            Some("use tracing::* for logging"),
        ),
        (
            "A2",
            "No panic on fallible path",
            'A',
            Severity::Critical,
            r"\.unwrap\(\)|\.expect\(|panic!|unreachable!",
            true,
            &["// SAFETY:", "// INVARIANT:"],
            None,
        ),
        (
            "A3",
            "No hardcoded secret/URL/subject",
            'A',
            Severity::Critical,
            r#"["'](gsk_|sk-|eyJ|postgres://|nats://|amqp://)|(api_key|password|secret|token)\s*=\s*["']"#,
            true,
            &[],
            None,
        ),
        (
            "A5",
            "Comments in English",
            'A',
            Severity::Minor,
            r"//.*\b(le|la|les|une|des|avec|pour|donnee|donnees|fichier|nous|vous|etre|cette)\b",
            false,
            &[],
            Some("heuristic: French words in comments"),
        ),
        (
            "A6",
            "No open-source attribution",
            'A',
            Severity::Major,
            r"(?i)\b(nuclei|wappalyzer|nmap|recog)\b",
            false,
            &[],
            None,
        ),
        (
            "A10",
            "Fail-safe default (no fail-open)",
            'A',
            Severity::Minor,
            r"unwrap_or\(\s*true\s*\)|unwrap_or_default\(\)",
            true,
            &[],
            Some("verify this does not open access on error"),
        ),
        (
            "B1",
            "No SQL injection (dynamic query)",
            'B',
            Severity::Critical,
            r#"format!\s*\(\s*["'].*(SELECT|INSERT|UPDATE|DELETE)"#,
            true,
            &[],
            None,
        ),
        (
            "B2",
            "No command injection",
            'B',
            Severity::Critical,
            r#"Command::new\(\s*["'](sh|bash)["']\)|\.arg\(\s*["']-c["']\s*\)"#,
            true,
            &[],
            None,
        ),
        (
            "B5",
            "Path traversal guard",
            'B',
            Severity::Major,
            r"File::open\(|fs::read\b|fs::read_to_string\(|fs::write\(",
            true,
            &[],
            Some("verify canonicalize + allowed-root prefix"),
        ),
        (
            "B6",
            "No error disclosure to client",
            'B',
            Severity::Major,
            r#"format!\(\s*["']\{:\?\}["']\s*,\s*\w*err"#,
            true,
            &[],
            Some("verify internal error is not returned in the HTTP body"),
        ),
        (
            "B9",
            "TLS verification",
            'B',
            Severity::Critical,
            r"danger_accept_invalid|set_verify\(\s*SslVerifyMode::NONE",
            true,
            &[],
            None,
        ),
        (
            "B10",
            "unsafe justified",
            'B',
            Severity::Major,
            r"\bunsafe\b",
            true,
            &["// SAFETY:"],
            Some("every unsafe block needs a // SAFETY: rationale"),
        ),
        (
            "C1",
            "No stub",
            'C',
            Severity::Major,
            r"todo!\(\)|unimplemented!\(\)|NOT_IMPLEMENTED",
            true,
            &[],
            None,
        ),
        (
            "C7",
            "serde JSON (no manual format)",
            'C',
            Severity::Minor,
            r#"format!\(\s*r?#*["'].*\{[^}]*\}.*["']"#,
            true,
            &[],
            Some("heuristic: build JSON with serde, not format!"),
        ),
        (
            "F1",
            "Event store immutability (I1)",
            'F',
            Severity::Critical,
            r"(?i)(UPDATE|DELETE)\b.{0,40}\bevent",
            true,
            &[],
            None,
        ),
        (
            "F4",
            "Deterministic replay (I4)",
            'F',
            Severity::Critical,
            r"SystemTime::now|Instant::now|rand::|thread_rng",
            true,
            &[],
            Some("forbidden in the decision path unless captured in the event"),
        ),
    ];

    raw.iter()
        .map(|(id, name, bloc, sev, pat, excl, allow, note)| {
            let regex = Regex::new(pat).with_context(|| format!("invalid regex for {id}"))?;
            Ok(PatternCheck {
                id,
                name,
                bloc: *bloc,
                severity: *sev,
                regex,
                exclude_test: *excl,
                allow_markers: allow,
                note: *note,
            })
        })
        .collect()
}

/// Run every check (pattern, structural, manual) over the scanned files.
pub fn run_all(files: &[PathBuf], root: &Path) -> Result<Vec<CheckResult>> {
    let checks = build()?;
    let mut results = Vec::new();

    // Pre-read files once (path + content + per-line test flags).
    let loaded: Vec<(String, String, Vec<bool>)> = files
        .iter()
        .filter_map(|p| {
            let content = scan::read_file(p)?;
            let test_flags = scan::test_lines(&content);
            let is_test_file = scan::is_test_path(p);
            // If the whole file is a test file, mark every line as test.
            let flags = if is_test_file {
                vec![true; test_flags.len()]
            } else {
                test_flags
            };
            Some((display_path(p, root), content, flags))
        })
        .collect();

    for check in &checks {
        let mut findings = Vec::new();
        for (path, content, flags) in &loaded {
            for (idx, line) in content.lines().enumerate() {
                if check.exclude_test && flags.get(idx).copied().unwrap_or(false) {
                    continue;
                }
                if check.allow_markers.iter().any(|m| line.contains(m)) {
                    continue;
                }
                if check.regex.is_match(line) {
                    findings.push(Finding {
                        file: path.clone(),
                        line: idx + 1,
                        excerpt: line.trim().chars().take(120).collect(),
                    });
                }
            }
        }
        results.push(if findings.is_empty() {
            let r = CheckResult::pass(check.id, check.name, check.bloc, check.severity);
            match check.note {
                Some(n) => r.with_note(n),
                None => r,
            }
        } else {
            CheckResult::fail(check.id, check.name, check.bloc, check.severity, findings)
        });
    }

    results.extend(structural_checks(files, root));
    results.extend(manual_checks());
    Ok(results)
}

/// Filesystem-level checks that are not line patterns.
fn structural_checks(files: &[PathBuf], root: &Path) -> Vec<CheckResult> {
    let mut out = Vec::new();

    // A9 -- Cargo.lock present at the crate root (supply-chain determinism).
    out.push(if root.join("Cargo.lock").is_file() {
        CheckResult::pass("A9", "Cargo.lock committed", 'A', Severity::Major)
    } else {
        CheckResult::na(
            "A9",
            "Cargo.lock committed",
            'A',
            Severity::Major,
            "Cargo.lock not found at crate root (required for cargo audit determinism)",
        )
    });

    // C10 -- at least one test module or tests/ file exists in scope.
    let has_tests = files.iter().any(|p| {
        scan::is_test_path(p)
            || scan::read_file(p)
                .is_some_and(|c| c.contains("#[cfg(test)]") || c.contains("#[test]"))
    });
    out.push(if has_tests {
        CheckResult::pass("C10", "Tests present", 'C', Severity::Major)
    } else {
        CheckResult::fail("C10", "Tests present", 'C', Severity::Major, Vec::new())
            .with_note("no #[cfg(test)] / #[test] / tests/ file found in scope")
    });

    out
}

/// Checks that require semantic or runtime analysis the static scanner cannot do
/// reliably; surfaced as N/A so a human (or apex/pdca) follows up. They are
/// excluded from scoring rather than guessed.
fn manual_checks() -> Vec<CheckResult> {
    const MANUAL: &[(&str, &str, char, Severity, &str)] = &[
        (
            "A4",
            "rustfmt clean",
            'A',
            Severity::Major,
            "covered by Bloc D3 (cargo fmt --check)",
        ),
        (
            "A7",
            "Public API documented",
            'A',
            Severity::Minor,
            "manual: every pub item has a /// doc-comment",
        ),
        (
            "A8",
            "RAII / no resource leak",
            'A',
            Severity::Major,
            "manual: no MutexGuard held across .await, no mem::forget",
        ),
        (
            "B3",
            "Hardcoded secrets",
            'B',
            Severity::Critical,
            "covered by A3",
        ),
        (
            "B4",
            "AuthN/Z + identity binding (I3)",
            'B',
            Severity::Critical,
            "manual: protected routes behind auth layer; action tied to agent_id",
        ),
        (
            "B7",
            "Security logging",
            'B',
            Severity::Major,
            "manual: attacks logged via tracing::warn target=security",
        ),
        (
            "B8",
            "Input validation at boundary",
            'B',
            Severity::Major,
            "manual: typed extractors, parse + validate",
        ),
        (
            "C2",
            "No mock data",
            'C',
            Severity::Major,
            "manual: values computed from real data, not literals",
        ),
        (
            "C3",
            "Async task cleanup",
            'C',
            Severity::Major,
            "manual: spawned tasks have JoinHandle / CancellationToken",
        ),
        (
            "C4",
            "Error wrapping / context",
            'C',
            Severity::Major,
            "manual: anyhow context / thiserror #[from] preserves source",
        ),
        (
            "C5",
            "Borrow vs clone",
            'C',
            Severity::Minor,
            "manual: covered by Bloc D1 clippy (rust-best-practices ch3)",
        ),
        (
            "C6",
            "Pool / client reuse",
            'C',
            Severity::Minor,
            "manual: shared Arc pool, not per-request",
        ),
        (
            "C8",
            "IDs typed (Uuid/Ulid)",
            'C',
            Severity::Major,
            "manual: parse at boundary before use",
        ),
        (
            "C9",
            "Pagination on list endpoints",
            'C',
            Severity::Minor,
            "manual: LIMIT/OFFSET or cursor",
        ),
        (
            "E1",
            "R17 test file present",
            'E',
            Severity::Critical,
            "manual: oneshot test invoking the handler",
        ),
        (
            "E2",
            "R17 test execution",
            'E',
            Severity::Critical,
            "manual: cargo test green (see Bloc D)",
        ),
        (
            "E3",
            "R17 live smoke curl",
            'E',
            Severity::Critical,
            "manual: real curl on the running gateway",
        ),
        (
            "E4",
            "R17 response envelope",
            'E',
            Severity::Major,
            "manual: frontend unwraps .data",
        ),
        (
            "F2",
            "Control-plane mediation (I2)",
            'F',
            Severity::Critical,
            "manual: no direct agent->external bypass",
        ),
        (
            "F3",
            "Side-effects mediated (I5)",
            'F',
            Severity::Critical,
            "manual: external effects via controlled proxies",
        ),
        (
            "F5",
            "Approval blocking (I6)",
            'F',
            Severity::Critical,
            "manual: action blocks until resolution or timeout",
        ),
    ];
    MANUAL
        .iter()
        .map(|(id, name, bloc, sev, note)| CheckResult::na(id, name, *bloc, *sev, *note))
        .collect()
}

/// Render a file path relative to `root` when possible, for compact reports.
fn display_path(p: &Path, root: &Path) -> String {
    p.strip_prefix(root).unwrap_or(p).display().to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn all_patterns_compile() {
        assert!(build().is_ok(), "every pattern regex must compile");
    }

    #[test]
    fn build_contains_expected_critical_checks() {
        let checks = build().expect("patterns compile");
        let critical: Vec<_> = checks
            .iter()
            .filter(|c| c.severity == Severity::Critical)
            .map(|c| c.id)
            .collect();
        for id in ["A1", "A2", "A3", "B1", "B2", "B9", "F1", "F4"] {
            assert!(
                critical.contains(&id),
                "{id} should be a critical pattern check"
            );
        }
    }
}
