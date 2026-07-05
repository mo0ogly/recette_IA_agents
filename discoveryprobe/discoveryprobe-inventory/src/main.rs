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
//! A second command, `passport issue`, is the I/O CONSUMER of the pure
//! `agent-passport` crate: it reads a 32-byte Ed25519 signing seed from the
//! `INSPECT_IA_AGENTS_PASSPORT_KEY` environment variable (hex), builds a
//! `SigningKey`, seals the supplied claims into a signed passport, and writes
//! it to `<tree>/.inspect_ia_agents/passport.json` (or `--out`). The seed is
//! read from the environment ONLY -- never hardcoded, never logged, never
//! echoed (R8). Any error before the write (missing/invalid key, issuing
//! failure) is fail-safe: NO passport file is produced.
//!
//! A third command, `passport verify`, is the fail-safe VERIFIER: it reads an
//! EXISTING `<tree>/.inspect_ia_agents/passport.json`, loads a trust file
//! (`--trust`, a JSON object `{ "<key_id>": "<pubkey_hex>", ... }`) into a
//! `TrustStore`, and checks the passport against an INJECTED clock (`--now`,
//! I4 -- never `SystemTime::now`) and an optional declared scope (`--declared`
//! csv, for the overreach check). The `Verdict` JSON is printed to stdout in
//! BOTH the trusted and untrusted cases (the JSON is the product); the exit
//! code is the gate. Task 7 owns the inventory-level "absent/unsigned" state;
//! this command verifies an EXISTING passport file, so an absent passport.json
//! is a plain error (exit 1), not a verdict.
//!
//! Conventions (same as discoveryprobe-catalog): no arg-parsing dependency,
//! errors on stderr only, JSON only on stdout. Exit codes: for `scan`/`passport
//! issue`, 0 success / 2 usage error / 1 any other error. For `passport verify`,
//! a richer gate contract: 0 Trusted, 3 Untrusted (verdict still printed),
//! 2 usage or config error (bad flags, unreadable/malformed `--trust`, malformed
//! `--now`), 1 io/other (absent or unparseable passport.json).

use std::collections::BTreeMap;
use std::fmt;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

use agent_passport::{issue, verify, Claims, DeclaredScope, Passport, Timestamp, TrustStore};
use discoveryprobe_inventory::correlate::correlate;
use discoveryprobe_inventory::graph::DeclaredGraph;
use discoveryprobe_inventory::model::ObservedInput;
use discoveryprobe_inventory::report::{self, ReportError};
use discoveryprobe_inventory::scan::{scan_tree, PassportStatus, ScanError};
use ed25519_dalek::SigningKey;

/// Environment variable carrying the Ed25519 signing seed (32-byte hex) used by
/// `passport issue`. Read at issue time only; never logged or echoed (R8).
const PASSPORT_KEY_ENV: &str = "INSPECT_IA_AGENTS_PASSPORT_KEY";

/// Multi-line usage string printed on any usage error, covering both commands.
const USAGE: &str = "usage:\n  discoveryprobe-inventory scan <path> [--capture <file.json>] [--team <dir>] [--out <file>]\n  discoveryprobe-inventory passport issue <tree> --agent-id <id> --tenant <t> --scope <a,b,c> --delegation <x,human:alice> --exp <rfc3339> --key-id <k> [--spiffe-id <spiffe://...>] [--out <file>]\n  discoveryprobe-inventory passport verify <tree> --trust <pubkeys.json> --now <rfc3339> [--declared <a,b,c>]";

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
    /// The signing key from the environment is absent, empty, or malformed.
    /// The message NEVER contains the key material (R8). Exits 2.
    Key(String),
    /// Sealing the passport (agent-passport `issue`) failed.
    Passport(agent_passport::PassportError),
    /// Serializing the issued passport (or a verdict) to JSON failed.
    Encode(String),
    /// The `--trust` file (verify) is absent, unreadable, not a JSON object of
    /// `{key_id: pubkey_hex}`, or carries an invalid key. A trust-anchor config
    /// error. Exits 2.
    TrustFile {
        /// The trust file path as given.
        path: String,
        /// The read, parse, or bad-key error message.
        message: String,
    },
    /// The injected `--now` clock (verify) is not a valid RFC3339 UTC timestamp.
    /// A config error. Exits 2.
    Clock(String),
    /// The passport file to verify could not be read (absent or unreadable).
    /// Exits 1 (io/other): this command verifies an EXISTING passport; the
    /// inventory-level "absent" state is Task 7's concern.
    PassportRead {
        /// The passport.json path as given.
        path: String,
        /// The I/O error message.
        message: String,
    },
    /// The passport file to verify could not be parsed as a passport. Exits 1:
    /// an unparseable file is an error, whereas a parseable-but-defective
    /// passport is a printed [`Verdict::Untrusted`] (exit 3), never an error.
    PassportParse {
        /// The passport.json path as given.
        path: String,
        /// The parse error message.
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
            CliError::Key(message) => write!(f, "signing key: {message}"),
            CliError::Passport(e) => write!(f, "passport issue failed: {e}"),
            CliError::Encode(message) => write!(f, "encode passport: {message}"),
            CliError::TrustFile { path, message } => write!(f, "trust file {path}: {message}"),
            CliError::Clock(message) => write!(f, "invalid --now: {message}"),
            CliError::PassportRead { path, message } => {
                write!(f, "read passport {path}: {message}")
            }
            CliError::PassportParse { path, message } => {
                write!(f, "parse passport {path}: {message}")
            }
        }
    }
}

impl std::error::Error for CliError {}

impl CliError {
    /// Process exit code for this error. Usage and config errors (bad flags,
    /// signing key, trust file, clock) exit 2; everything else exits 1. The
    /// Untrusted verdict is NOT an error -- it is a printed verdict with exit 3
    /// (see [`Outcome`]).
    fn exit_code(&self) -> u8 {
        match self {
            CliError::Usage(_)
            | CliError::Key(_)
            | CliError::TrustFile { .. }
            | CliError::Clock(_) => 2,
            _ => 1,
        }
    }
}

/// The parsed top-level command.
#[derive(Debug, PartialEq, Eq)]
enum Command {
    /// `scan <path> [...]` -- the static inventory pipeline.
    Scan(ScanArgs),
    /// `passport issue <tree> [...]` -- seal claims into a signed passport.
    PassportIssue(PassportIssueArgs),
    /// `passport verify <tree> [...]` -- fail-safe verification of a passport.
    PassportVerify(PassportVerifyArgs),
}

/// Parsed command line of the `scan` command.
#[derive(Debug, PartialEq, Eq)]
struct ScanArgs {
    /// The source tree to scan.
    path: PathBuf,
    /// Optional `ObservedInput` JSON file.
    capture: Option<PathBuf>,
    /// Optional directory holding orchestration `team.json` files.
    team: Option<PathBuf>,
    /// Optional output file for the JSON (default: stdout).
    out: Option<PathBuf>,
}

/// Parsed command line of the `passport issue` subcommand.
#[derive(Debug, PartialEq, Eq)]
struct PassportIssueArgs {
    /// The agent tree the passport belongs to (default output location root).
    tree: PathBuf,
    /// The agent identity -- becomes `Claims.id`.
    agent_id: String,
    /// The tenant the agent runs under.
    tenant: String,
    /// The action-family scope (comma-separated on the CLI).
    scope: Vec<String>,
    /// The delegation chain, terminal entry a human principal (comma-separated).
    delegation: Vec<String>,
    /// The RFC3339 UTC expiry timestamp.
    exp: String,
    /// The identifier of the key that seals (and later verifies) the passport.
    key_id: String,
    /// Optional SPIFFE identity.
    spiffe_id: Option<String>,
    /// Optional output file (default: `<tree>/.inspect_ia_agents/passport.json`).
    out: Option<PathBuf>,
}

/// Parsed command line of the `passport verify` subcommand.
#[derive(Debug, PartialEq, Eq)]
struct PassportVerifyArgs {
    /// The agent tree whose `.inspect_ia_agents/passport.json` is verified.
    tree: PathBuf,
    /// The trust file: a JSON object `{ "<key_id>": "<pubkey_hex>", ... }`.
    trust: PathBuf,
    /// The injected clock as RFC3339 UTC (I4: never the system clock).
    now: String,
    /// Optional declared action families (comma-separated) for the overreach
    /// check; absent means no scope check is performed.
    declared: Option<Vec<String>>,
}

/// Parses program arguments (without argv[0]) into a [`Command`]. The first
/// token selects the command; `scan` and `passport` are the only two.
fn parse_command(args: &[String]) -> Result<Command, CliError> {
    let mut iter = args.iter();
    match iter.next().map(String::as_str) {
        Some("scan") => parse_scan(iter.as_slice()).map(Command::Scan),
        Some("passport") => parse_passport(iter.as_slice()),
        Some(other) => Err(CliError::Usage(format!("unknown command '{other}'"))),
        None => Err(CliError::Usage("missing command".to_string())),
    }
}

/// Parses the arguments that follow the `scan` command token.
fn parse_scan(args: &[String]) -> Result<ScanArgs, CliError> {
    let mut iter = args.iter();
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
    Ok(ScanArgs {
        path,
        capture,
        team,
        out,
    })
}

/// Parses the arguments that follow the `passport` command token, dispatching
/// on the subcommand: `issue` (seal claims) or `verify` (fail-safe check).
fn parse_passport(args: &[String]) -> Result<Command, CliError> {
    let mut iter = args.iter();
    match iter.next().map(String::as_str) {
        Some("issue") => parse_passport_issue(iter.as_slice()).map(Command::PassportIssue),
        Some("verify") => parse_passport_verify(iter.as_slice()).map(Command::PassportVerify),
        Some(other) => Err(CliError::Usage(format!(
            "unknown passport subcommand '{other}'"
        ))),
        None => Err(CliError::Usage("missing passport subcommand".to_string())),
    }
}

/// Parses the flags of `passport issue`. All of agent-id/tenant/scope/
/// delegation/exp/key-id are REQUIRED; a missing one is a usage error.
fn parse_passport_issue(args: &[String]) -> Result<PassportIssueArgs, CliError> {
    let mut iter = args.iter();
    let tree = match iter.next() {
        Some(p) if !p.starts_with("--") => PathBuf::from(p),
        _ => {
            return Err(CliError::Usage(
                "missing <tree> for passport issue".to_string(),
            ))
        }
    };

    let mut agent_id: Option<String> = None;
    let mut tenant: Option<String> = None;
    let mut scope: Option<Vec<String>> = None;
    let mut delegation: Option<Vec<String>> = None;
    let mut exp: Option<String> = None;
    let mut key_id: Option<String> = None;
    let mut spiffe_id: Option<String> = None;
    let mut out: Option<PathBuf> = None;

    while let Some(flag) = iter.next() {
        let Some(value) = iter.next() else {
            return Err(CliError::Usage(format!("{flag} requires a value")));
        };
        match flag.as_str() {
            "--agent-id" => set_once(&mut agent_id, value.clone(), flag)?,
            "--tenant" => set_once(&mut tenant, value.clone(), flag)?,
            "--exp" => set_once(&mut exp, value.clone(), flag)?,
            "--key-id" => set_once(&mut key_id, value.clone(), flag)?,
            "--spiffe-id" => set_once(&mut spiffe_id, value.clone(), flag)?,
            "--scope" => set_once(&mut scope, parse_csv(value, flag)?, flag)?,
            "--delegation" => set_once(&mut delegation, parse_csv(value, flag)?, flag)?,
            "--out" => set_once(&mut out, PathBuf::from(value), flag)?,
            other => return Err(CliError::Usage(format!("unknown argument '{other}'"))),
        }
    }

    Ok(PassportIssueArgs {
        tree,
        agent_id: require(agent_id, "--agent-id")?,
        tenant: require(tenant, "--tenant")?,
        scope: require(scope, "--scope")?,
        delegation: require(delegation, "--delegation")?,
        exp: require(exp, "--exp")?,
        key_id: require(key_id, "--key-id")?,
        spiffe_id,
        out,
    })
}

/// Parses the flags of `passport verify`. `--trust` and `--now` are REQUIRED;
/// `--declared` is optional. A missing required flag is a usage error.
fn parse_passport_verify(args: &[String]) -> Result<PassportVerifyArgs, CliError> {
    let mut iter = args.iter();
    let tree = match iter.next() {
        Some(p) if !p.starts_with("--") => PathBuf::from(p),
        _ => {
            return Err(CliError::Usage(
                "missing <tree> for passport verify".to_string(),
            ))
        }
    };

    let mut trust: Option<PathBuf> = None;
    let mut now: Option<String> = None;
    let mut declared: Option<Vec<String>> = None;

    while let Some(flag) = iter.next() {
        let Some(value) = iter.next() else {
            return Err(CliError::Usage(format!("{flag} requires a value")));
        };
        match flag.as_str() {
            "--trust" => set_once(&mut trust, PathBuf::from(value), flag)?,
            "--now" => set_once(&mut now, value.clone(), flag)?,
            "--declared" => set_once(&mut declared, parse_csv(value, flag)?, flag)?,
            other => return Err(CliError::Usage(format!("unknown argument '{other}'"))),
        }
    }

    Ok(PassportVerifyArgs {
        tree,
        trust: require(trust, "--trust")?,
        now: require(now, "--now")?,
        declared,
    })
}

/// Assigns `value` into `slot`, rejecting a second occurrence of `flag`.
fn set_once<T>(slot: &mut Option<T>, value: T, flag: &str) -> Result<(), CliError> {
    if slot.is_some() {
        return Err(CliError::Usage(format!("{flag} given twice")));
    }
    *slot = Some(value);
    Ok(())
}

/// Unwraps a required flag value, mapping absence to a usage error.
fn require<T>(slot: Option<T>, flag: &str) -> Result<T, CliError> {
    slot.ok_or_else(|| CliError::Usage(format!("missing required {flag}")))
}

/// Splits a comma-separated flag value into trimmed, non-empty entries. An
/// empty overall value or any empty entry is a usage error.
fn parse_csv(raw: &str, flag: &str) -> Result<Vec<String>, CliError> {
    let items: Vec<String> = raw.split(',').map(|s| s.trim().to_string()).collect();
    if items.iter().any(String::is_empty) {
        return Err(CliError::Usage(format!(
            "{flag} has an empty entry in {raw:?}"
        )));
    }
    Ok(items)
}

/// A successful command result: the STDOUT payload plus the process exit code.
///
/// Most commands succeed with exit 0; `passport verify` uses the exit code as a
/// GATE (0 Trusted, 3 Untrusted) while still emitting the verdict JSON on
/// stdout, so the outcome carries the code explicitly.
#[derive(Debug)]
struct Outcome {
    /// The payload to print on stdout (empty when it went to `--out`).
    stdout: String,
    /// The process exit code.
    code: u8,
}

impl Outcome {
    /// A plain success (exit 0) carrying `stdout`.
    fn success(stdout: String) -> Self {
        Outcome { stdout, code: 0 }
    }
}

/// Dispatches the parsed command. Returns the STDOUT payload and exit code (the
/// payload may be empty when the output went to a file instead).
fn run(args: &[String]) -> Result<Outcome, CliError> {
    match parse_command(args)? {
        Command::Scan(scan) => run_scan(scan).map(Outcome::success),
        Command::PassportIssue(issue_args) => run_passport_issue(issue_args).map(Outcome::success),
        Command::PassportVerify(verify_args) => run_passport_verify(verify_args),
    }
}

/// Runs the `scan` command: scan, build the declared graph (passports +
/// teams), correlate with the optional capture, serialize. Returns the payload
/// for STDOUT: the inventory JSON, or an empty string when `--out` already
/// consumed it (JSON goes to exactly one place).
fn run_scan(cli: ScanArgs) -> Result<String, CliError> {
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

/// Runs `passport issue`: load the signing seed from the environment, seal the
/// claims into a signed passport, and write it to disk. Fail-safe: the seed is
/// resolved and the passport issued+encoded BEFORE any filesystem write, so no
/// passport file is ever produced on an error path. Returns a short
/// confirmation naming the file (the key is never echoed). R8.
fn run_passport_issue(args: PassportIssueArgs) -> Result<String, CliError> {
    let seed = load_signing_seed()?;
    let signing_key = SigningKey::from_bytes(&seed);

    let claims = Claims {
        id: args.agent_id,
        tenant: args.tenant,
        delegation: args.delegation,
        scope: args.scope,
        exp: args.exp,
        spiffe_id: args.spiffe_id,
    };
    let passport = issue(claims, &signing_key, &args.key_id).map_err(CliError::Passport)?;
    let json =
        serde_json::to_string_pretty(&passport).map_err(|e| CliError::Encode(e.to_string()))?;

    let out_path = args
        .out
        .unwrap_or_else(|| args.tree.join(".inspect_ia_agents").join("passport.json"));
    if let Some(parent) = out_path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| CliError::Write {
            path: parent.display().to_string(),
            message: e.to_string(),
        })?;
    }
    std::fs::write(&out_path, &json).map_err(|e| CliError::Write {
        path: out_path.display().to_string(),
        message: e.to_string(),
    })?;
    Ok(format!("passport written to {}", out_path.display()))
}

/// Runs `passport verify`: load the trust file and the injected clock (config;
/// any failure exits 2), read+parse the EXISTING passport (absent/unparseable
/// exits 1), then run the pure fail-safe [`verify`]. The [`Verdict`] JSON is
/// returned on stdout in BOTH the trusted and untrusted cases; the exit code is
/// the gate (0 Trusted, 3 Untrusted). I4: `--now` is the ONLY clock -- the
/// system clock is never read.
fn run_passport_verify(args: PassportVerifyArgs) -> Result<Outcome, CliError> {
    // Config first (exit 2 on failure): trust anchors and the injected clock.
    let trust = load_trust_store(&args.trust)?;
    let now = Timestamp::parse(&args.now).map_err(|e| CliError::Clock(e.to_string()))?;

    // Read + parse the EXISTING passport (exit 1 on absent/unparseable).
    let passport_path = args.tree.join(".inspect_ia_agents").join("passport.json");
    let raw = std::fs::read(&passport_path).map_err(|e| CliError::PassportRead {
        path: passport_path.display().to_string(),
        message: e.to_string(),
    })?;
    let passport = Passport::from_json(&raw).map_err(|e| CliError::PassportParse {
        path: passport_path.display().to_string(),
        message: e.to_string(),
    })?;

    // Optional declared scope drives the overreach check; absent -> None.
    let declared = args.declared.map(DeclaredScope::new);
    let verdict = verify(&passport, &trust, &now, declared.as_ref());
    let json =
        serde_json::to_string_pretty(&verdict).map_err(|e| CliError::Encode(e.to_string()))?;

    // The JSON is the product (printed either way); the exit code is the gate.
    let code = if verdict.is_trusted() { 0 } else { 3 };
    Ok(Outcome { stdout: json, code })
}

/// Loads a [`TrustStore`] from a JSON object file `{ "<key_id>": "<pubkey_hex>",
/// ... }`. Every failure (unreadable file, non-object JSON, or an invalid key)
/// is a [`CliError::TrustFile`] (config, exit 2). A [`BTreeMap`] is used so the
/// insertion order is deterministic (I4), though the store itself is unordered
/// for lookup.
fn load_trust_store(path: &Path) -> Result<TrustStore, CliError> {
    let trust_error = |message: String| CliError::TrustFile {
        path: path.display().to_string(),
        message,
    };
    let raw = std::fs::read_to_string(path).map_err(|e| trust_error(e.to_string()))?;
    let entries: BTreeMap<String, String> =
        serde_json::from_str(&raw).map_err(|e| trust_error(e.to_string()))?;
    let mut trust = TrustStore::new();
    for (key_id, pubkey_hex) in &entries {
        trust
            .add_hex(key_id, pubkey_hex)
            .map_err(|e| trust_error(e.to_string()))?;
    }
    Ok(trust)
}

/// Reads and decodes the Ed25519 signing seed from [`PASSPORT_KEY_ENV`].
///
/// Returns [`CliError::Key`] (exit 2, fail-safe) when the variable is absent,
/// empty, or not exactly 32 bytes of hex. The error message NEVER contains the
/// key material (R8).
fn load_signing_seed() -> Result<[u8; 32], CliError> {
    let raw = match std::env::var(PASSPORT_KEY_ENV) {
        Ok(value) if !value.trim().is_empty() => value,
        _ => {
            return Err(CliError::Key(format!(
                "{PASSPORT_KEY_ENV} is not set (expected 32-byte hex seed)"
            )))
        }
    };
    decode_seed_hex(raw.trim()).ok_or_else(|| {
        CliError::Key(format!(
            "{PASSPORT_KEY_ENV} must be 32 bytes of hex (64 hex characters)"
        ))
    })
}

/// Decodes exactly 64 hex characters into a 32-byte seed, or `None` on any
/// wrong length or non-hex character.
fn decode_seed_hex(text: &str) -> Option<[u8; 32]> {
    if text.len() != 64 {
        return None;
    }
    let bytes = text.as_bytes();
    let mut out = [0u8; 32];
    for (i, slot) in out.iter_mut().enumerate() {
        let hi = hex_digit(bytes[i * 2])?;
        let lo = hex_digit(bytes[i * 2 + 1])?;
        *slot = (hi << 4) | lo;
    }
    Some(out)
}

/// Maps a single ASCII hex digit byte to its value (0-15), or `None`.
fn hex_digit(byte: u8) -> Option<u8> {
    match byte {
        b'0'..=b'9' => Some(byte - b'0'),
        b'a'..=b'f' => Some(byte - b'a' + 10),
        b'A'..=b'F' => Some(byte - b'A' + 10),
        _ => None,
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
        Ok(outcome) => {
            if !outcome.stdout.is_empty() {
                println!("{}", outcome.stdout);
            }
            ExitCode::from(outcome.code)
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
        let json = run(&args(&["scan", &corpus("repos/gh-pr-bot/repo")]))
            .expect("run")
            .stdout;
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
        .expect("run")
        .stdout;
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
        .expect("run")
        .stdout;
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
        .expect("run")
        .stdout;
        assert!(stdout_payload.is_empty());
        let written = std::fs::read_to_string(&out_path).expect("read out file");
        let inventory: AgentInventory = serde_json::from_str(&written).expect("parse");
        assert_eq!(inventory.agents.len(), 1);
        std::fs::remove_file(&out_path).expect("cleanup");
    }
}
