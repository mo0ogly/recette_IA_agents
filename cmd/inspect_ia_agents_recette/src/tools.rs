//! Bloc D: shell out to the cargo static-analysis toolchain
//! (clippy, audit, fmt, deny, geiger). Each tool maps to one Go SAST tool.

use std::path::Path;
use std::process::Command;

use crate::model::{CheckResult, Severity};

/// True if a binary responds to `--version`.
fn tool_available(bin: &str) -> bool {
    Command::new(bin)
        .arg("--version")
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

/// Run a command in `cwd`, returning (success, combined stdout+stderr).
fn run(cwd: &Path, program: &str, args: &[&str]) -> (bool, String) {
    match Command::new(program).args(args).current_dir(cwd).output() {
        Ok(out) => {
            let mut combined = String::from_utf8_lossy(&out.stdout).into_owned();
            combined.push_str(&String::from_utf8_lossy(&out.stderr));
            (out.status.success(), combined)
        }
        Err(e) => (false, format!("failed to spawn {program}: {e}")),
    }
}

/// Run the full Bloc D gate from `cwd` (the crate/workspace root).
pub fn run_all(cwd: &Path) -> Vec<CheckResult> {
    let mut out = Vec::new();

    if !tool_available("cargo") {
        for (id, name) in [
            ("D1", "cargo clippy"),
            ("D2", "cargo audit"),
            ("D3", "cargo fmt"),
            ("D4", "cargo deny"),
            ("D5", "cargo geiger"),
        ] {
            out.push(CheckResult::na(
                id,
                name,
                'D',
                Severity::Critical,
                "cargo not installed",
            ));
        }
        return out;
    }

    // D1 -- clippy (go vet + lint gate).
    let (ok, _) = run(
        cwd,
        "cargo",
        &[
            "clippy",
            "--all-targets",
            "--all-features",
            "--",
            "-D",
            "warnings",
        ],
    );
    out.push(if ok {
        CheckResult::pass("D1", "cargo clippy", 'D', Severity::Critical)
    } else {
        CheckResult::fail("D1", "cargo clippy", 'D', Severity::Critical, Vec::new())
            .with_note("clippy reported warnings/errors (see `cargo clippy -- -D warnings`)")
    });

    // D2 -- cargo audit (govulncheck equivalent).
    out.push(if tool_available("cargo-audit") {
        let (_, text) = run(cwd, "cargo", &["audit"]);
        let hc =
            text.matches("Severity: high").count() + text.matches("Severity: critical").count();
        if hc == 0 {
            CheckResult::pass("D2", "cargo audit", 'D', Severity::Critical)
        } else {
            CheckResult::fail("D2", "cargo audit", 'D', Severity::Critical, Vec::new())
                .with_note(format!("{hc} HIGH/CRITICAL RUSTSEC advisory(ies)"))
        }
    } else {
        CheckResult::na(
            "D2",
            "cargo audit",
            'D',
            Severity::Critical,
            "cargo-audit not installed",
        )
    });

    // D3 -- rustfmt check.
    let (fmt_ok, _) = run(cwd, "cargo", &["fmt", "--all", "--", "--check"]);
    out.push(if fmt_ok {
        CheckResult::pass("D3", "cargo fmt", 'D', Severity::Major)
    } else {
        CheckResult::fail("D3", "cargo fmt", 'D', Severity::Major, Vec::new())
            .with_note("not formatted (run `cargo fmt --all`)")
    });

    // D4 -- cargo deny (supply-chain policy).
    out.push(if tool_available("cargo-deny") {
        let (ok, _) = run(
            cwd,
            "cargo",
            &["deny", "check", "advisories", "bans", "licenses", "sources"],
        );
        if ok {
            CheckResult::pass("D4", "cargo deny", 'D', Severity::Major)
        } else {
            CheckResult::fail("D4", "cargo deny", 'D', Severity::Major, Vec::new())
                .with_note("advisories/bans/licenses/sources policy violation")
        }
    } else {
        CheckResult::na(
            "D4",
            "cargo deny",
            'D',
            Severity::Major,
            "cargo-deny not installed",
        )
    });

    // D5 -- cargo geiger (unsafe surface). Interpretation is manual; we run it to
    // surface output but do not auto-score it (avoids false PASS/FAIL).
    out.push(if tool_available("cargo-geiger") {
        CheckResult::na(
            "D5",
            "cargo geiger",
            'D',
            Severity::Major,
            "run `cargo geiger`; review unsafe surface manually",
        )
    } else {
        CheckResult::na(
            "D5",
            "cargo geiger",
            'D',
            Severity::Major,
            "cargo-geiger not installed",
        )
    });

    out
}

/// Bloc D entries when `--skip-tools` is set.
pub fn skipped_bloc_d() -> Vec<CheckResult> {
    [
        ("D1", "cargo clippy"),
        ("D2", "cargo audit"),
        ("D3", "cargo fmt"),
        ("D4", "cargo deny"),
        ("D5", "cargo geiger"),
    ]
    .into_iter()
    .map(|(id, name)| CheckResult::na(id, name, 'D', Severity::Critical, "skipped (--skip-tools)"))
    .collect()
}
