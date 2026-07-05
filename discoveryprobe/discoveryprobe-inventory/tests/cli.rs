//! Integration tests: drive the compiled `discoveryprobe-inventory` binary
//! end-to-end (real process, real corpus tree) and assert the CLI contract:
//! JSON only on stdout, errors + usage on stderr, exit 0 / 2.

use discoveryprobe_inventory::model::AgentInventory;
use discoveryprobe_inventory::scan::PassportStatus;
use ed25519_dalek::SigningKey;
use std::path::PathBuf;
use std::process::Command;

/// Path of the compiled binary under test (provided by cargo).
const BIN: &str = env!("CARGO_BIN_EXE_discoveryprobe-inventory");

/// Environment variable carrying the Ed25519 signing seed for `passport issue`.
const KEY_ENV: &str = "INSPECT_IA_AGENTS_PASSPORT_KEY";

/// A fixed 32-byte test seed (all `0x07`) as 64 lowercase hex characters.
fn test_seed_hex() -> String {
    "07".repeat(32)
}

/// The raw 32-byte seed matching [`test_seed_hex`].
fn test_seed_bytes() -> [u8; 32] {
    [0x07u8; 32]
}

/// Encodes bytes as lowercase hexadecimal (two digits per byte).
fn to_hex(bytes: &[u8]) -> String {
    let mut out = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        out.push_str(&format!("{byte:02x}"));
    }
    out
}

/// Creates (and returns) a fresh, unique temporary directory for a test tree.
fn unique_temp_dir(tag: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!(
        "discoveryprobe-inv-{tag}-{}-{}",
        std::process::id(),
        tag.len()
    ));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).expect("create temp tree");
    dir
}

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

#[test]
fn passport_issue_writes_a_verifiable_signed_passport() {
    let tree = unique_temp_dir("issue-ok");
    let output = Command::new(BIN)
        .env(KEY_ENV, test_seed_hex())
        .args([
            "passport",
            "issue",
            &tree.display().to_string(),
            "--agent-id",
            "acme-pr-bot",
            "--tenant",
            "acme",
            "--scope",
            "read_repo,open_pr",
            "--delegation",
            "svc:ci,human:alice",
            "--exp",
            "2999-01-01T00:00:00Z",
            "--key-id",
            "acme-key-1",
        ])
        .output()
        .expect("spawn binary");
    assert!(
        output.status.success(),
        "exit: {:?}, stderr: {}",
        output.status.code(),
        String::from_utf8_lossy(&output.stderr)
    );
    // The confirmation names the file; the key is never echoed.
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("passport.json"), "stdout: {stdout}");
    assert!(!stdout.contains(&test_seed_hex()), "seed leaked on stdout");

    let path = tree.join(".inspect_ia_agents").join("passport.json");
    assert!(path.exists(), "expected passport at {}", path.display());

    // End-to-end: the emitted file parses and VERIFIES Trusted against the
    // matching public key with a `now` before `exp`.
    let raw = std::fs::read(&path).expect("read passport");
    let passport = agent_passport::Passport::from_json(&raw).expect("parse passport");
    let signing = SigningKey::from_bytes(&test_seed_bytes());
    let pubkey_hex = to_hex(&signing.verifying_key().to_bytes());
    let mut trust = agent_passport::TrustStore::new();
    trust.add_hex("acme-key-1", &pubkey_hex).expect("add key");
    let now = agent_passport::Timestamp::parse("2026-01-01T00:00:00Z").expect("now");
    let verdict = agent_passport::verify(&passport, &trust, &now, None);
    assert!(verdict.is_trusted(), "verdict: {verdict:?}");

    let _ = std::fs::remove_dir_all(&tree);
}

#[test]
fn passport_issue_is_deterministic() {
    let common = [
        "--agent-id",
        "det-bot",
        "--tenant",
        "acme",
        "--scope",
        "read_repo",
        "--delegation",
        "human:alice",
        "--exp",
        "2999-01-01T00:00:00Z",
        "--key-id",
        "acme-key-1",
    ];
    let run_once = |tag: &str| -> Vec<u8> {
        let tree = unique_temp_dir(tag);
        let mut argv = vec![
            "passport".to_string(),
            "issue".to_string(),
            tree.display().to_string(),
        ];
        argv.extend(common.iter().map(|s| s.to_string()));
        let status = Command::new(BIN)
            .env(KEY_ENV, test_seed_hex())
            .args(&argv)
            .status()
            .expect("spawn binary");
        assert!(status.success());
        let bytes = std::fs::read(tree.join(".inspect_ia_agents").join("passport.json"))
            .expect("read passport");
        let _ = std::fs::remove_dir_all(&tree);
        bytes
    };
    // Ed25519 signing is deterministic: same args + same key -> identical bytes.
    assert_eq!(run_once("det-a"), run_once("det-b"));
}

#[test]
fn passport_issue_without_key_env_fails_and_writes_no_file() {
    let tree = unique_temp_dir("issue-nokey");
    let output = Command::new(BIN)
        .env_remove(KEY_ENV)
        .args([
            "passport",
            "issue",
            &tree.display().to_string(),
            "--agent-id",
            "a",
            "--tenant",
            "t",
            "--scope",
            "read_repo",
            "--delegation",
            "human:alice",
            "--exp",
            "2999-01-01T00:00:00Z",
            "--key-id",
            "k",
        ])
        .output()
        .expect("spawn binary");
    assert_eq!(
        output.status.code(),
        Some(2),
        "stderr: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    let path = tree.join(".inspect_ia_agents").join("passport.json");
    assert!(
        !path.exists(),
        "no passport must be written without a signing key"
    );
    let _ = std::fs::remove_dir_all(&tree);
}

#[test]
fn passport_issue_missing_required_flag_is_usage_error() {
    // Missing --key-id.
    let output = Command::new(BIN)
        .env(KEY_ENV, test_seed_hex())
        .args([
            "passport",
            "issue",
            "/tmp/does-not-matter",
            "--agent-id",
            "a",
            "--tenant",
            "t",
            "--scope",
            "read_repo",
            "--delegation",
            "human:alice",
            "--exp",
            "2999-01-01T00:00:00Z",
        ])
        .output()
        .expect("spawn binary");
    assert_eq!(output.status.code(), Some(2), "missing flag must exit 2");
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("usage"), "stderr: {stderr}");
}
