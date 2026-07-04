//! Integration tests: drive the compiled `discoveryprobe-inventory` binary
//! end-to-end (real process, real corpus tree) and assert the CLI contract:
//! JSON only on stdout, errors + usage on stderr, exit 0 / 2.

use discoveryprobe_inventory::model::AgentInventory;
use discoveryprobe_inventory::scan::PassportStatus;
use std::path::PathBuf;
use std::process::Command;

/// Path of the compiled binary under test (provided by cargo).
const BIN: &str = env!("CARGO_BIN_EXE_discoveryprobe-inventory");

/// Resolves a path under the repo `corpus/` directory. Tests run from the
/// crate dir (`discoveryprobe/discoveryprobe-inventory/`), so corpus is two
/// levels up from `CARGO_MANIFEST_DIR`.
fn corpus_path(rel: &str) -> String {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../corpus")
        .join(rel)
        .display()
        .to_string()
}

#[test]
fn scan_of_the_pr_bot_corpus_repo_prints_a_parseable_inventory() {
    let output = Command::new(BIN)
        .args(["scan", &corpus_path("repos/gh-pr-bot/repo")])
        .output()
        .expect("spawn binary");
    assert!(
        output.status.success(),
        "exit: {:?}, stderr: {}",
        output.status.code(),
        String::from_utf8_lossy(&output.stderr)
    );
    // JSON only on stdout: the whole stdout parses as an AgentInventory.
    let stdout = String::from_utf8(output.stdout).expect("utf8 stdout");
    let inventory: AgentInventory = serde_json::from_str(stdout.trim()).expect("parse inventory");
    assert_eq!(inventory.agents.len(), 1);
    assert!(
        matches!(inventory.agents[0].passport, PassportStatus::Present { .. }),
        "expected a present passport, got {:?}",
        inventory.agents[0].passport
    );
    // The kind-tagged JSON contract holds on the wire too.
    assert!(stdout.contains(r#""kind":"present""#), "{stdout}");
}

#[test]
fn no_args_is_a_usage_error_on_stderr_with_nonzero_exit() {
    let output = Command::new(BIN).output().expect("spawn binary");
    assert!(!output.status.success());
    assert_eq!(output.status.code(), Some(2), "usage errors exit 2");
    // Nothing on stdout, usage on stderr.
    assert!(output.stdout.is_empty());
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("usage"), "stderr: {stderr}");
    assert!(
        stderr.contains("discoveryprobe-inventory scan <path>"),
        "stderr: {stderr}"
    );
}
