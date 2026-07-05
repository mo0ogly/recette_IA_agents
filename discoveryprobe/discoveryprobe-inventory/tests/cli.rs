//! Integration tests: drive the compiled `discoveryprobe-inventory` binary
//! end-to-end (real process, real corpus tree) and assert the CLI contract:
//! JSON only on stdout, errors + usage on stderr, exit 0 / 2.

use discoveryprobe_inventory::model::AgentInventory;
use discoveryprobe_inventory::scan::PassportStatus;
use ed25519_dalek::SigningKey;
use std::path::{Path, PathBuf};
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

// --- passport verify subcommand -------------------------------------------
//
// Exit-code contract of `passport verify`: 0 trusted, 3 untrusted (verdict
// still printed), 2 usage/config (bad flags, unreadable/malformed trust file,
// malformed --now), 1 io/other (absent or unparseable passport.json).

/// The public-key hex matching [`test_seed_bytes`] (what a trust file records).
fn test_pubkey_hex() -> String {
    to_hex(
        &SigningKey::from_bytes(&test_seed_bytes())
            .verifying_key()
            .to_bytes(),
    )
}

/// Issues a signed passport into a fresh tree via the `passport issue`
/// subcommand (reusing the Task 5 flow) and returns the tree path. The passport
/// is sealed under key_id `acme-key-1` with the given `scope` and `exp`.
fn issue_passport(tag: &str, scope: &str, exp: &str) -> PathBuf {
    let tree = unique_temp_dir(tag);
    let status = Command::new(BIN)
        .env(KEY_ENV, test_seed_hex())
        .args([
            "passport",
            "issue",
            &tree.display().to_string(),
            "--agent-id",
            "verify-bot",
            "--tenant",
            "acme",
            "--scope",
            scope,
            "--delegation",
            "svc:ci,human:alice",
            "--exp",
            exp,
            "--key-id",
            "acme-key-1",
        ])
        .status()
        .expect("spawn issue");
    assert!(status.success(), "issue must succeed to seed a verify test");
    tree
}

/// Writes a JSON trust file (`{key_id: pubkey_hex, ...}`) under `dir` and
/// returns its path.
fn write_trust_file(dir: &Path, entries: &[(&str, &str)]) -> PathBuf {
    let map: std::collections::BTreeMap<String, String> = entries
        .iter()
        .map(|(k, v)| ((*k).to_string(), (*v).to_string()))
        .collect();
    let path = dir.join("trust.json");
    std::fs::write(&path, serde_json::to_string(&map).expect("encode trust"))
        .expect("write trust file");
    path
}

#[test]
fn passport_verify_trusted_before_exp_exits_zero() {
    let tree = issue_passport("verify-ok", "read_repo,open_pr", "2999-01-01T00:00:00Z");
    let trust = write_trust_file(&tree, &[("acme-key-1", &test_pubkey_hex())]);
    let output = Command::new(BIN)
        .args([
            "passport",
            "verify",
            &tree.display().to_string(),
            "--trust",
            &trust.display().to_string(),
            "--now",
            "2026-01-01T00:00:00Z",
        ])
        .output()
        .expect("spawn verify");
    assert_eq!(
        output.status.code(),
        Some(0),
        "trusted must exit 0, stderr: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    let stdout = String::from_utf8(output.stdout).expect("utf8 stdout");
    let verdict: serde_json::Value = serde_json::from_str(stdout.trim()).expect("parse verdict");
    assert_eq!(verdict["kind"], "trusted", "{stdout}");
    let _ = std::fs::remove_dir_all(&tree);
}

#[test]
fn passport_verify_after_exp_is_untrusted_expired_exit_3() {
    let tree = issue_passport("verify-expired", "read_repo", "2026-01-01T00:00:00Z");
    let trust = write_trust_file(&tree, &[("acme-key-1", &test_pubkey_hex())]);
    let output = Command::new(BIN)
        .args([
            "passport",
            "verify",
            &tree.display().to_string(),
            "--trust",
            &trust.display().to_string(),
            "--now",
            "2027-01-01T00:00:00Z",
        ])
        .output()
        .expect("spawn verify");
    assert_eq!(
        output.status.code(),
        Some(3),
        "untrusted must exit 3, stderr: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    let stdout = String::from_utf8(output.stdout).expect("utf8 stdout");
    let verdict: serde_json::Value = serde_json::from_str(stdout.trim()).expect("parse verdict");
    assert_eq!(verdict["kind"], "untrusted", "{stdout}");
    let reasons = verdict["reasons"].as_array().expect("reasons array");
    assert!(
        reasons.iter().any(|r| r["kind"] == "expired"),
        "expected an expired reason: {stdout}"
    );
    let _ = std::fs::remove_dir_all(&tree);
}

#[test]
fn passport_verify_empty_trust_is_untrusted_unknown_key_exit_3() {
    let tree = issue_passport("verify-nokey", "read_repo", "2999-01-01T00:00:00Z");
    // An empty trust store: the key_id is unknown, so the signature is uncheckable.
    let trust = write_trust_file(&tree, &[]);
    let output = Command::new(BIN)
        .args([
            "passport",
            "verify",
            &tree.display().to_string(),
            "--trust",
            &trust.display().to_string(),
            "--now",
            "2026-01-01T00:00:00Z",
        ])
        .output()
        .expect("spawn verify");
    assert_eq!(output.status.code(), Some(3), "untrusted must exit 3");
    let stdout = String::from_utf8(output.stdout).expect("utf8 stdout");
    let verdict: serde_json::Value = serde_json::from_str(stdout.trim()).expect("parse verdict");
    assert_eq!(verdict["kind"], "untrusted", "{stdout}");
    let reasons = verdict["reasons"].as_array().expect("reasons array");
    assert!(
        reasons.iter().any(|r| r["kind"] == "unknown_key_id"),
        "expected an unknown_key_id reason: {stdout}"
    );
    let _ = std::fs::remove_dir_all(&tree);
}

#[test]
fn passport_verify_declared_overreach_is_untrusted_exit_3() {
    let tree = issue_passport("verify-overreach", "read_repo", "2999-01-01T00:00:00Z");
    let trust = write_trust_file(&tree, &[("acme-key-1", &test_pubkey_hex())]);
    let output = Command::new(BIN)
        .args([
            "passport",
            "verify",
            &tree.display().to_string(),
            "--trust",
            &trust.display().to_string(),
            "--now",
            "2026-01-01T00:00:00Z",
            "--declared",
            "read_repo,delete_everything",
        ])
        .output()
        .expect("spawn verify");
    assert_eq!(output.status.code(), Some(3), "overreach must exit 3");
    let stdout = String::from_utf8(output.stdout).expect("utf8 stdout");
    let verdict: serde_json::Value = serde_json::from_str(stdout.trim()).expect("parse verdict");
    assert_eq!(verdict["kind"], "untrusted", "{stdout}");
    let reasons = verdict["reasons"].as_array().expect("reasons array");
    let overreach = reasons
        .iter()
        .find(|r| r["kind"] == "scope_overreach")
        .expect("expected a scope_overreach reason");
    let extra = overreach["extra"].as_array().expect("extra array");
    assert!(
        extra.iter().any(|e| e == "delete_everything"),
        "extra must list the ungranted family: {stdout}"
    );
    let _ = std::fs::remove_dir_all(&tree);
}

#[test]
fn passport_verify_absent_passport_exits_one() {
    // A tree with a valid trust file but NO passport.json.
    let tree = unique_temp_dir("verify-absent");
    let trust = write_trust_file(&tree, &[("acme-key-1", &test_pubkey_hex())]);
    let output = Command::new(BIN)
        .args([
            "passport",
            "verify",
            &tree.display().to_string(),
            "--trust",
            &trust.display().to_string(),
            "--now",
            "2026-01-01T00:00:00Z",
        ])
        .output()
        .expect("spawn verify");
    assert_eq!(
        output.status.code(),
        Some(1),
        "absent passport must exit 1, stderr: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(
        output.stdout.is_empty(),
        "no verdict when the passport is absent"
    );
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("passport.json"), "clear message: {stderr}");
    let _ = std::fs::remove_dir_all(&tree);
}

#[test]
fn passport_verify_malformed_trust_file_exits_two() {
    let tree = issue_passport("verify-badtrust", "read_repo", "2999-01-01T00:00:00Z");
    let trust = tree.join("trust.json");
    std::fs::write(&trust, "not json at all").expect("write bad trust");
    let output = Command::new(BIN)
        .args([
            "passport",
            "verify",
            &tree.display().to_string(),
            "--trust",
            &trust.display().to_string(),
            "--now",
            "2026-01-01T00:00:00Z",
        ])
        .output()
        .expect("spawn verify");
    assert_eq!(
        output.status.code(),
        Some(2),
        "malformed trust file is a config error (exit 2)"
    );
    let _ = std::fs::remove_dir_all(&tree);
}

#[test]
fn passport_verify_missing_now_is_usage_error_exit_two() {
    let tree = issue_passport("verify-nonow", "read_repo", "2999-01-01T00:00:00Z");
    let trust = write_trust_file(&tree, &[("acme-key-1", &test_pubkey_hex())]);
    let output = Command::new(BIN)
        .args([
            "passport",
            "verify",
            &tree.display().to_string(),
            "--trust",
            &trust.display().to_string(),
        ])
        .output()
        .expect("spawn verify");
    assert_eq!(output.status.code(), Some(2), "missing --now must exit 2");
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("usage"), "stderr: {stderr}");
    let _ = std::fs::remove_dir_all(&tree);
}

#[test]
fn passport_verify_is_deterministic() {
    let tree = issue_passport("verify-det", "read_repo", "2999-01-01T00:00:00Z");
    let trust = write_trust_file(&tree, &[("acme-key-1", &test_pubkey_hex())]);
    let run_once = || -> Vec<u8> {
        let output = Command::new(BIN)
            .args([
                "passport",
                "verify",
                &tree.display().to_string(),
                "--trust",
                &trust.display().to_string(),
                "--now",
                "2026-01-01T00:00:00Z",
            ])
            .output()
            .expect("spawn verify");
        assert_eq!(output.status.code(), Some(0));
        output.stdout
    };
    // verify() is pure and --now is the only clock: identical stdout across runs.
    assert_eq!(run_once(), run_once());
    let _ = std::fs::remove_dir_all(&tree);
}

#[test]
fn passport_verify_trust_file_as_json_array_exits_two() {
    let tree = issue_passport("verify-array-trust", "read_repo", "2999-01-01T00:00:00Z");
    let trust = tree.join("trust_array.json");
    // Trust file is a JSON array instead of an object.
    std::fs::write(&trust, "[]").expect("write array trust");
    let output = Command::new(BIN)
        .args([
            "passport",
            "verify",
            &tree.display().to_string(),
            "--trust",
            &trust.display().to_string(),
            "--now",
            "2026-01-01T00:00:00Z",
        ])
        .output()
        .expect("spawn verify");
    assert_eq!(
        output.status.code(),
        Some(2),
        "JSON array trust file is a config error (exit 2)"
    );
    let _ = std::fs::remove_dir_all(&tree);
}

#[test]
fn passport_verify_trust_file_with_bad_hex_pubkey_exits_two() {
    let tree = issue_passport("verify-badhex-trust", "read_repo", "2999-01-01T00:00:00Z");
    let trust = tree.join("trust_badhex.json");
    // Trust file has a bad-hex pubkey value (not valid hex).
    std::fs::write(&trust, r#"{"acme-key-1":"nothex"}"#).expect("write badhex trust");
    let output = Command::new(BIN)
        .args([
            "passport",
            "verify",
            &tree.display().to_string(),
            "--trust",
            &trust.display().to_string(),
            "--now",
            "2026-01-01T00:00:00Z",
        ])
        .output()
        .expect("spawn verify");
    assert_eq!(
        output.status.code(),
        Some(2),
        "bad-hex pubkey in trust file is a config error (exit 2)"
    );
    let _ = std::fs::remove_dir_all(&tree);
}

#[test]
fn passport_verify_corrupt_passport_json_exits_one() {
    let tree = issue_passport("verify-corrupt", "read_repo", "2999-01-01T00:00:00Z");
    // Overwrite the valid passport with valid JSON that is not a passport.
    let passport_path = tree.join(".inspect_ia_agents").join("passport.json");
    std::fs::write(&passport_path, r#"{"hello":"world"}"#).expect("write corrupt passport");
    let trust = write_trust_file(&tree, &[("acme-key-1", &test_pubkey_hex())]);
    let output = Command::new(BIN)
        .args([
            "passport",
            "verify",
            &tree.display().to_string(),
            "--trust",
            &trust.display().to_string(),
            "--now",
            "2026-01-01T00:00:00Z",
        ])
        .output()
        .expect("spawn verify");
    assert_eq!(
        output.status.code(),
        Some(1),
        "corrupt passport (parse error) must exit 1, stderr: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    // No verdict on stdout when the passport fails to parse.
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(
        !stdout.contains("kind"),
        "no verdict when passport is corrupt (not a valid passport): {stdout}"
    );
    let _ = std::fs::remove_dir_all(&tree);
}

#[test]
fn passport_verify_malformed_now_flag_exits_two() {
    let tree = issue_passport("verify-badnow", "read_repo", "2999-01-01T00:00:00Z");
    let trust = write_trust_file(&tree, &[("acme-key-1", &test_pubkey_hex())]);
    let output = Command::new(BIN)
        .args([
            "passport",
            "verify",
            &tree.display().to_string(),
            "--trust",
            &trust.display().to_string(),
            "--now",
            "not-a-timestamp",
        ])
        .output()
        .expect("spawn verify");
    assert_eq!(
        output.status.code(),
        Some(2),
        "malformed --now is a config error (exit 2), stderr: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    let _ = std::fs::remove_dir_all(&tree);
}
