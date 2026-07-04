//! discoveryprobe-inventory CLI: scan a source tree into an agent inventory.
//!
//! Runs the static pipeline (scan -> declared graph -> correlate -> JSON) and
//! prints the `AgentInventory` report. Usage:
//!   discoveryprobe-inventory scan <path> [--capture <file.json>] [--team <dir>] [--out <file>]
//!
//! - `<path>`: the source tree to scan (`scan::scan_tree`).
//! - `--capture`: an `ObservedInput` JSON file (runtime observation). Absent
//!   means a static-only run, whose conformity can never be `Conform`
//!   (fail-safe, see the lib doc).
//! - `--team`: a directory walked recursively (sorted) for `team.json` files.
//!   The declared graph is passports + teams: the merged `from_passport`
//!   graphs of every scanned Present passport, unioned with every
//!   `from_team_json` graph found under the directory.
//! - `--out`: write the JSON to that file instead of stdout.
//!
//! Conventions (same as discoveryprobe-catalog): no arg-parsing dependency,
//! errors on stderr only, JSON only on stdout. Exit codes: 0 success,
//! 2 usage error, 1 any other error.

use std::fmt;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

use discoveryprobe_inventory::correlate::correlate;
use discoveryprobe_inventory::graph::DeclaredGraph;
use discoveryprobe_inventory::model::ObservedInput;
use discoveryprobe_inventory::report::{self, ReportError};
use discoveryprobe_inventory::scan::{scan_tree, PassportStatus, ScanError};

/// One-line usage string printed on any usage error.
const USAGE: &str = "usage: discoveryprobe-inventory scan <path> [--capture <file.json>] [--team <dir>] [--out <file>]";

/// Errors of the CLI layer. Everything is rendered to stderr via `Display`;
/// `Usage` exits 2, every other variant exits 1.
#[derive(Debug)]
enum CliError {
    /// The command line does not match the usage contract.
    Usage(String),
    /// The tree scan failed (unreadable directory or manifest).
    Scan(ScanError),
    /// The capture file could not be read or parsed as `ObservedInput`.
    Capture {
        /// The capture file path as given.
        path: String,
        /// The read or parse error message.
        message: String,
    },
    /// A team.json (or the team directory walk) could not be read or parsed.
    Team {
        /// The offending path (directory or team.json file).
        path: String,
        /// The read or parse error message.
        message: String,
    },
    /// Serializing the inventory failed.
    Report(ReportError),
    /// Writing the `--out` file failed.
    Write {
        /// The output file path as given.
        path: String,
        /// The I/O error message.
        message: String,
    },
}

impl fmt::Display for CliError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            CliError::Usage(msg) => write!(f, "usage error: {msg}"),
            CliError::Scan(e) => write!(f, "scan failed: {e}"),
            CliError::Capture { path, message } => write!(f, "capture {path}: {message}"),
            CliError::Team { path, message } => write!(f, "team {path}: {message}"),
            CliError::Report(e) => write!(f, "{e}"),
            CliError::Write { path, message } => write!(f, "write {path}: {message}"),
        }
    }
}

impl std::error::Error for CliError {}

impl CliError {
    /// Process exit code for this error: 2 for usage, 1 otherwise.
    fn exit_code(&self) -> u8 {
        match self {
            CliError::Usage(_) => 2,
            _ => 1,
        }
    }
}

/// Parsed command line of the `scan` command.
#[derive(Debug, PartialEq, Eq)]
struct CliArgs {
    /// The source tree to scan.
    path: PathBuf,
    /// Optional `ObservedInput` JSON file.
    capture: Option<PathBuf>,
    /// Optional directory holding orchestration `team.json` files.
    team: Option<PathBuf>,
    /// Optional output file for the JSON (default: stdout).
    out: Option<PathBuf>,
}

/// Parses program arguments (without argv[0]) into `CliArgs`.
fn parse_args(args: &[String]) -> Result<CliArgs, CliError> {
    let mut iter = args.iter();
    match iter.next().map(String::as_str) {
        Some("scan") => {}
        Some(other) => return Err(CliError::Usage(format!("unknown command '{other}'"))),
        None => return Err(CliError::Usage("missing command".to_string())),
    }
    let path = match iter.next() {
        Some(p) if !p.starts_with("--") => PathBuf::from(p),
        _ => return Err(CliError::Usage("missing <path> to scan".to_string())),
    };
    let mut capture: Option<PathBuf> = None;
    let mut team: Option<PathBuf> = None;
    let mut out: Option<PathBuf> = None;
    while let Some(flag) = iter.next() {
        let slot = match flag.as_str() {
            "--capture" => &mut capture,
            "--team" => &mut team,
            "--out" => &mut out,
            other => return Err(CliError::Usage(format!("unknown argument '{other}'"))),
        };
        let Some(value) = iter.next() else {
            return Err(CliError::Usage(format!("{flag} requires a value")));
        };
        if slot.is_some() {
            return Err(CliError::Usage(format!("{flag} given twice")));
        }
        *slot = Some(PathBuf::from(value));
    }
    Ok(CliArgs {
        path,
        capture,
        team,
        out,
    })
}

/// Runs the CLI: scan, build the declared graph (passports + teams),
/// correlate with the optional capture, serialize. Returns the payload for
/// STDOUT: the inventory JSON, or an empty string when `--out` already
/// consumed it (JSON goes to exactly one place).
fn run(args: &[String]) -> Result<String, CliError> {
    let cli = parse_args(args)?;
    let scanned = scan_tree(&cli.path).map_err(CliError::Scan)?;

    // Declared graph = passports + teams (module doc): every scanned Present
    // passport contributes its handoff edges, then every team.json under
    // --team is merged in. All merges are sorted+deduplicated (I4).
    let mut declared = DeclaredGraph::default();
    for agent in &scanned {
        if let PassportStatus::Present { passport } = &agent.passport {
            declared = declared.merge(DeclaredGraph::from_passport(passport));
        }
    }
    if let Some(team_dir) = &cli.team {
        for team_file in team_json_files(team_dir)? {
            let raw = std::fs::read_to_string(&team_file).map_err(|e| CliError::Team {
                path: team_file.display().to_string(),
                message: e.to_string(),
            })?;
            let graph = DeclaredGraph::from_team_json(&raw).map_err(|e| CliError::Team {
                path: team_file.display().to_string(),
                message: e.to_string(),
            })?;
            declared = declared.merge(graph);
        }
    }

    // Absent capture = static-only run (observed = None, never Conform).
    let observed: Option<ObservedInput> = match &cli.capture {
        Some(capture_path) => {
            let raw = std::fs::read_to_string(capture_path).map_err(|e| CliError::Capture {
                path: capture_path.display().to_string(),
                message: e.to_string(),
            })?;
            let input = serde_json::from_str(&raw).map_err(|e| CliError::Capture {
                path: capture_path.display().to_string(),
                message: e.to_string(),
            })?;
            Some(input)
        }
        None => None,
    };

    let inventory = correlate(&scanned, &declared, observed.as_ref());
    let json = report::to_json(&inventory).map_err(CliError::Report)?;
    match &cli.out {
        Some(out_path) => {
            std::fs::write(out_path, &json).map_err(|e| CliError::Write {
                path: out_path.display().to_string(),
                message: e.to_string(),
            })?;
            Ok(String::new())
        }
        None => Ok(json),
    }
}

/// Collects every file named `team.json` under `dir`, recursively, in sorted
/// order (I4). An unreadable directory is an error, never a silent empty
/// graph (fail-safe).
fn team_json_files(dir: &Path) -> Result<Vec<PathBuf>, CliError> {
    let mut files = Vec::new();
    collect_team_json(dir, &mut files)?;
    files.sort();
    Ok(files)
}

/// Depth-first collection helper for `team_json_files`.
fn collect_team_json(dir: &Path, out: &mut Vec<PathBuf>) -> Result<(), CliError> {
    let entries = std::fs::read_dir(dir).map_err(|e| CliError::Team {
        path: dir.display().to_string(),
        message: e.to_string(),
    })?;
    for entry in entries {
        let entry = entry.map_err(|e| CliError::Team {
            path: dir.display().to_string(),
            message: e.to_string(),
        })?;
        let path = entry.path();
        if path.is_dir() {
            collect_team_json(&path, out)?;
        } else if path.file_name().and_then(|n| n.to_str()) == Some("team.json") {
            out.push(path);
        }
    }
    Ok(())
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match run(&args) {
        Ok(stdout_payload) => {
            if !stdout_payload.is_empty() {
                println!("{stdout_payload}");
            }
            ExitCode::SUCCESS
        }
        Err(err) => {
            eprintln!("{err}");
            if matches!(err, CliError::Usage(_)) {
                eprintln!("{USAGE}");
            }
            ExitCode::from(err.exit_code())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use discoveryprobe_inventory::model::{AgentInventory, Conformity};

    /// Resolves a path under the repo `corpus/` directory (the crate lives
    /// at `discoveryprobe/discoveryprobe-inventory/`).
    fn corpus(rel: &str) -> String {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../corpus")
            .join(rel)
            .display()
            .to_string()
    }

    /// Resolves a committed fixture under `tests/fixtures/<name>`.
    fn fixture(name: &str) -> String {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("tests/fixtures")
            .join(name)
            .display()
            .to_string()
    }

    /// Shorthand: owned args vector from string literals.
    fn args(list: &[&str]) -> Vec<String> {
        list.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn missing_command_and_unknown_flags_are_usage_errors() {
        for bad in [
            args(&[]),
            args(&["frobnicate"]),
            args(&["scan"]),
            args(&["scan", "--capture", "x.json"]), // flag where <path> expected
            args(&["scan", "tree", "--bogus", "x"]),
            args(&["scan", "tree", "--capture"]), // missing value
            args(&["scan", "tree", "--out", "a", "--out", "b"]),
        ] {
            let err = run(&bad).expect_err("expected usage error");
            assert!(matches!(err, CliError::Usage(_)), "{bad:?} -> {err}");
            assert_eq!(err.exit_code(), 2);
        }
    }

    #[test]
    fn static_scan_of_the_corpus_pr_bot_yields_one_not_observed_agent() {
        let json = run(&args(&["scan", &corpus("repos/gh-pr-bot/repo")])).expect("run");
        let inventory: AgentInventory = serde_json::from_str(&json).expect("parse");
        assert_eq!(inventory.agents.len(), 1);
        assert_eq!(inventory.agents[0].agent_id, "acme-dependency-pr-bot[bot]");
        // Static-only: never Conform (fail-safe).
        assert_eq!(inventory.agents[0].conformity, Conformity::NotObserved);
    }

    #[test]
    fn team_dir_feeds_the_declared_graph() {
        let json = run(&args(&[
            "scan",
            &corpus("repos/gh-pr-bot/repo"),
            "--team",
            &corpus("maf_orchestration/correct/finance-approval-handoff-correct"),
        ]))
        .expect("run");
        let inventory: AgentInventory = serde_json::from_str(&json).expect("parse");
        // The finance team.json declares 4 handoff edges (see graph tests).
        assert_eq!(inventory.comm_graph.declared_edges.len(), 4);
    }

    #[test]
    fn capture_file_makes_an_in_scope_agent_conform() {
        let json = run(&args(&[
            "scan",
            &corpus("repos/gh-pr-bot/repo"),
            "--capture",
            &fixture("capture-pr-bot.json"),
        ]))
        .expect("run");
        let inventory: AgentInventory = serde_json::from_str(&json).expect("parse");
        assert_eq!(inventory.agents.len(), 1);
        // The fixture records the declared open_pr action: Conform.
        assert_eq!(inventory.agents[0].conformity, Conformity::Conform);
        assert_eq!(inventory.agents[0].observed.actions, vec!["open_pr"]);
    }

    #[test]
    fn out_flag_writes_the_json_and_leaves_stdout_empty() {
        let out_path = std::env::temp_dir().join("discoveryprobe-inventory-out-test.json");
        let stdout_payload = run(&args(&[
            "scan",
            &corpus("repos/gh-pr-bot/repo"),
            "--out",
            &out_path.display().to_string(),
        ]))
        .expect("run");
        assert!(stdout_payload.is_empty());
        let written = std::fs::read_to_string(&out_path).expect("read out file");
        let inventory: AgentInventory = serde_json::from_str(&written).expect("parse");
        assert_eq!(inventory.agents.len(), 1);
        std::fs::remove_file(&out_path).expect("cleanup");
    }
}
