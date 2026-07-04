//! Passport parsing: reads and validates the agent passport (what an agent
//! DECLARES about itself). Two shapes coexist in the corpus:
//!
//! - the REPO shape (`corpus/repos/<slug>/repo/.inspect_ia_agents/manifest.json`):
//!   `{schema_version, agent: {name, target_system, identity, capabilities}}`;
//! - the UNIFIED shape (`corpus/schemas/agent-manifest.schema.json`, used by
//!   `corpus/agents/` and `corpus/maf_agents/`): top-level `kind`
//!   (`git_agent` | `maf_agent`), `agent_id`, `target_systems`,
//!   `declared_identity`, `capability_scope` (git or MAF capability items).
//!
//! `Passport::parse` tries the repo shape first, then the unified shape; when
//! both fail, the error reports BOTH shape errors so a broken manifest explains
//! itself to an auditor (these strings surface in `PassportStatus::Invalid`).
//!
//! Failure mode (fail-safe): any structural gap (missing/empty principal,
//! target, capabilities) is an error naming the field -- never a lenient parse.

use serde::{Deserialize, Serialize};
use std::fmt;

/// Parse/validation error for an agent passport.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PassportError {
    /// The document is not valid JSON at all.
    InvalidJson(String),
    /// The document is JSON but matches neither passport shape; both
    /// per-shape error lists are carried so the manifest explains itself.
    ShapeMismatch {
        /// Why the repo shape (`{schema_version, agent: {...}}`) was rejected.
        repo: String,
        /// Why the unified corpus shape (`{agent_id, capability_scope, ...}`)
        /// was rejected.
        unified: String,
    },
}

impl fmt::Display for PassportError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            PassportError::InvalidJson(e) => write!(f, "invalid JSON: {e}"),
            PassportError::ShapeMismatch { repo, unified } => write!(
                f,
                "manifest matches neither passport shape; repo shape: {repo}; unified shape: {unified}"
            ),
        }
    }
}

impl std::error::Error for PassportError {}

/// A parsed, validated agent passport (either corpus shape).
///
/// NOTE: intentionally NOT `kind`-tagged (externally-tagged serde default,
/// `{"Repo": {...}}`), unlike the bridge-crossing enums in `model.rs`. The
/// Python bridge and the console never dispatch on this wire shape; they read
/// the pre-extracted `declared` profile and the `kind()` accessor instead.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum Passport {
    /// Repo passport: `.inspect_ia_agents/manifest.json` inside a publishable repo.
    Repo(RepoManifest),
    /// Unified corpus manifest (`corpus/agents/`, `corpus/maf_agents/`).
    /// Boxed: this variant is much larger than `Repo` (clippy large_enum_variant).
    Unified(Box<UnifiedManifest>),
}

// ---------------------------------------------------------------------------
// Repo shape (verified against corpus/repos/gh-pr-bot/repo/.inspect_ia_agents/manifest.json)
// ---------------------------------------------------------------------------

/// Repo passport: `{schema_version, agent: {...}}`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RepoManifest {
    /// Passport schema version (e.g. "1.0").
    pub schema_version: Option<String>,
    /// The declared agent.
    pub agent: RepoAgent,
}

/// The `agent` object of the repo passport shape.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RepoAgent {
    /// Human-readable agent name.
    pub name: Option<String>,
    /// Free-text description.
    pub description: Option<String>,
    /// Single target system (e.g. "github").
    pub target_system: Option<String>,
    /// Declared identity (auth_method + principal).
    pub identity: Option<RepoIdentity>,
    /// Declared capabilities (action/mode/resources).
    pub capabilities: Option<Vec<RepoCapability>>,
}

/// Declared identity of a repo-shape passport.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RepoIdentity {
    /// Authentication method (e.g. "github_app", "pat").
    pub auth_method: Option<String>,
    /// Declared principal (bot username, app slug).
    pub principal: Option<String>,
}

/// One declared capability of a repo-shape passport.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RepoCapability {
    /// Canonical action type (e.g. "read_repo", "open_pr").
    pub action: Option<String>,
    /// Access mode ("read" | "write").
    pub mode: Option<String>,
    /// Repo globs the action is allowed on.
    pub resources: Option<Vec<String>>,
}

// ---------------------------------------------------------------------------
// Unified shape (verified against corpus/schemas/agent-manifest.schema.json)
// ---------------------------------------------------------------------------

/// Unified corpus manifest: `kind` discriminates git_agent vs maf_agent.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct UnifiedManifest {
    /// Subject family: "git_agent" | "maf_agent". Absent defaults to
    /// git_agent (backward compatibility, per the schema).
    pub kind: Option<String>,
    /// Stable unique id (slug).
    pub agent_id: Option<String>,
    /// Human-readable agent name.
    pub name: Option<String>,
    /// Free-text description.
    pub description: Option<String>,
    /// Provenance when imported from an external standard (e.g. MAF).
    pub source: Option<UnifiedSource>,
    /// Systems the agent acts on (git: github/gitlab; MAF: provider/runtime ids).
    pub target_systems: Option<Vec<String>>,
    /// Declared identity: git agents declare auth_method+principal,
    /// MAF agents declare provider+model.
    pub declared_identity: Option<UnifiedIdentity>,
    /// Declared allowed actions (git or MAF capability items).
    pub capability_scope: Option<Vec<UnifiedCapability>>,
    /// Runtime flags (lab_mode / real_mode).
    pub runtime: Option<UnifiedRuntime>,
    /// Manifest version (semver).
    pub version: Option<String>,
}

/// Provenance block of an imported standard agent.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct UnifiedSource {
    /// Standard name, e.g. "microsoft-agent-framework".
    pub standard: Option<String>,
    /// MAF top-level `kind` (e.g. "Prompt").
    pub maf_kind: Option<String>,
}

/// Declared identity of a unified manifest (git or MAF variant).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct UnifiedIdentity {
    /// Git variant: authentication method.
    pub auth_method: Option<String>,
    /// Git variant: declared principal.
    pub principal: Option<String>,
    /// MAF variant: model provider (e.g. "AzureOpenAI").
    pub provider: Option<String>,
    /// MAF variant: model id (may be an "=Env.X" reference).
    pub model: Option<String>,
    /// MAF variant: connection kind (e.g. "remote").
    pub connection_kind: Option<String>,
    /// Env var name holding the credential (never the secret itself).
    pub key_ref: Option<String>,
}

/// One capability item of a unified manifest. The three schema variants
/// (git action, invoke_tool, handoff) share one permissive struct; shape
/// validation happens post-parse so errors name the offending field.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct UnifiedCapability {
    /// Git action name, or "invoke_tool" / "handoff" for MAF items.
    pub action: Option<String>,
    /// Git variant: access mode ("read" | "write").
    pub mode: Option<String>,
    /// Git variant: repo globs.
    pub resources: Option<Vec<String>>,
    /// MAF invoke_tool variant: tool kind (mcp, function, web_search, ...).
    pub tool_kind: Option<String>,
    /// MAF variant: tool target or handoff target agent id.
    pub target: Option<String>,
    /// MAF invoke_tool variant: approval requirement ("never" | "always").
    pub approval: Option<String>,
}

/// Runtime flags of a unified manifest.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct UnifiedRuntime {
    /// Implementation language (informational).
    pub language: Option<String>,
    /// Relative path to the agent runnable, when present.
    pub entrypoint: Option<String>,
    /// Runs against the simulated lab.
    pub lab_mode: Option<bool>,
    /// Runs against real test orgs/repos with real credentials.
    pub real_mode: Option<bool>,
}

impl Passport {
    /// Parses an agent passport from raw JSON, trying the repo shape first,
    /// then the unified shape. On failure the error reports BOTH shape errors.
    pub fn parse(raw: &str) -> Result<Passport, PassportError> {
        let value: serde_json::Value =
            serde_json::from_str(raw).map_err(|e| PassportError::InvalidJson(e.to_string()))?;
        let repo_err = match try_repo(&value) {
            Ok(m) => return Ok(Passport::Repo(m)),
            Err(e) => e,
        };
        match try_unified(&value) {
            Ok(m) => Ok(Passport::Unified(Box::new(m))),
            Err(unified_err) => Err(PassportError::ShapeMismatch {
                repo: repo_err,
                unified: unified_err,
            }),
        }
    }

    /// Subject family: "git_agent" or "maf_agent". The repo shape and a
    /// unified manifest without `kind` both default to "git_agent".
    pub fn kind(&self) -> &str {
        match self {
            Passport::Repo(_) => "git_agent",
            Passport::Unified(m) => m.kind.as_deref().unwrap_or("git_agent"),
        }
    }

    /// Declared principal. For a MAF identity (no principal) this is the
    /// composed "provider:model" pair, documented stand-in for the principal.
    pub fn principal(&self) -> String {
        match self {
            Passport::Repo(m) => m
                .agent
                .identity
                .as_ref()
                .and_then(|i| i.principal.clone())
                .unwrap_or_default(),
            Passport::Unified(m) => {
                let identity = m.declared_identity.as_ref();
                if let Some(p) = identity.and_then(|i| i.principal.as_deref()) {
                    if !p.is_empty() {
                        return p.to_string();
                    }
                }
                let provider = identity.and_then(|i| i.provider.as_deref()).unwrap_or("");
                let model = identity.and_then(|i| i.model.as_deref()).unwrap_or("");
                format!("{provider}:{model}")
            }
        }
    }

    /// Primary target system. The repo shape has exactly one; for the unified
    /// multi-target shape this is the FIRST of the SORTED `target_systems`
    /// (deterministic representative, I4-stable across serializations).
    pub fn target_system(&self) -> String {
        self.target_systems().into_iter().next().unwrap_or_default()
    }

    /// ALL declared target systems, sorted and deduplicated. The repo shape
    /// wraps its single `agent.target_system` in a one-element vec; the
    /// unified shape yields every entry of `target_systems`. Correlators MUST
    /// use this (not the singular primary) so a multi-target MAF agent is not
    /// flagged with a false UndeclaredAction on its secondary targets.
    pub fn target_systems(&self) -> Vec<String> {
        let mut targets: Vec<String> = match self {
            Passport::Repo(m) => m.agent.target_system.clone().into_iter().collect(),
            Passport::Unified(m) => m.target_systems.clone().unwrap_or_default(),
        };
        targets.sort();
        targets.dedup();
        targets
    }

    /// Declared stable agent id (slug). Only the unified corpus shape carries
    /// one (`agent_id`); the repo shape has no id field, so this is `None`
    /// there (callers key repo passports by their filesystem slug instead).
    pub fn agent_id(&self) -> Option<&str> {
        match self {
            Passport::Repo(_) => None,
            Passport::Unified(m) => m.agent_id.as_deref(),
        }
    }

    /// Declared action names, sorted and deduplicated. Git items yield their
    /// canonical action (read_repo, open_pr, ...); MAF items yield
    /// "invoke_tool" / "handoff".
    pub fn actions(&self) -> Vec<String> {
        let mut actions: Vec<String> = match self {
            Passport::Repo(m) => m
                .agent
                .capabilities
                .iter()
                .flatten()
                .filter_map(|c| c.action.clone())
                .collect(),
            Passport::Unified(m) => m
                .capability_scope
                .iter()
                .flatten()
                .filter_map(|c| c.action.clone())
                .collect(),
        };
        actions.sort();
        actions.dedup();
        actions
    }

    /// Declared handoff target agent ids, sorted and deduplicated.
    /// Empty for git agents and for MAF agents without handoff capabilities.
    pub fn handoffs(&self) -> Vec<String> {
        let mut targets: Vec<String> = match self {
            Passport::Repo(_) => Vec::new(),
            Passport::Unified(m) => m
                .capability_scope
                .iter()
                .flatten()
                .filter(|c| c.action.as_deref() == Some("handoff"))
                .filter_map(|c| c.target.clone())
                .collect(),
        };
        targets.sort();
        targets.dedup();
        targets
    }
}

/// Canonical git action names, copied VERBATIM from the unified schema enum
/// (`corpus/schemas/agent-manifest.schema.json`, capability_scope git variant,
/// `properties.action.enum`). Guards the unified git capability arm only: the
/// repo shape (`.inspect_ia_agents/manifest.json`) is NOT enum-bound by any
/// schema in `corpus/schemas/` (the recette validates only
/// `discovery-ground-truth.json` for discovery repos), so repo capabilities
/// stay unguarded by design.
/// Also reused by `scan` as the canonical action vocabulary for the
/// OpenAPI shadow-agent heuristic (single source, never redeclared).
pub(crate) const KNOWN_GIT_ACTIONS: &[&str] = &[
    "read_repo",
    "list_repos",
    "open_issue",
    "comment_issue",
    "open_pr",
    "merge_pr",
    "push",
    "manage_webhook",
    "manage_release",
    "read_ci",
    "trigger_ci",
];

/// Returns true for a missing or empty string field.
fn blank(s: &Option<String>) -> bool {
    s.as_deref().map(str::is_empty).unwrap_or(true)
}

/// Tries the repo shape; on rejection returns a message listing every
/// missing/empty field (auditor-facing, joined with "; ").
fn try_repo(value: &serde_json::Value) -> Result<RepoManifest, String> {
    let manifest: RepoManifest =
        serde_json::from_value(value.clone()).map_err(|e| e.to_string())?;
    let mut errors: Vec<String> = Vec::new();
    let agent = &manifest.agent;
    if blank(&agent.name) {
        errors.push("agent.name is missing or empty".to_string());
    }
    if blank(&agent.target_system) {
        errors.push("agent.target_system is missing or empty".to_string());
    }
    match &agent.identity {
        None => errors.push("agent.identity is missing".to_string()),
        Some(identity) => {
            if blank(&identity.principal) {
                errors.push("agent.identity.principal is missing or empty".to_string());
            }
        }
    }
    match &agent.capabilities {
        None => errors.push("agent.capabilities is missing".to_string()),
        Some(caps) if caps.is_empty() => {
            errors.push("agent.capabilities is empty".to_string());
        }
        Some(caps) => {
            for (i, cap) in caps.iter().enumerate() {
                if blank(&cap.action) {
                    errors.push(format!(
                        "agent.capabilities[{i}].action is missing or empty"
                    ));
                }
            }
        }
    }
    if errors.is_empty() {
        Ok(manifest)
    } else {
        Err(errors.join("; "))
    }
}

/// Tries the unified corpus shape; on rejection returns a message listing
/// every missing/empty/inconsistent field (auditor-facing, joined with "; ").
fn try_unified(value: &serde_json::Value) -> Result<UnifiedManifest, String> {
    let manifest: UnifiedManifest =
        serde_json::from_value(value.clone()).map_err(|e| e.to_string())?;
    let mut errors: Vec<String> = Vec::new();
    if blank(&manifest.agent_id) {
        errors.push("agent_id is missing or empty".to_string());
    }
    if let Some(kind) = manifest.kind.as_deref() {
        if kind != "git_agent" && kind != "maf_agent" {
            errors.push(format!("kind '{kind}' is not git_agent or maf_agent"));
        }
    }
    match &manifest.target_systems {
        None => errors.push("target_systems is missing".to_string()),
        Some(t) if t.is_empty() => errors.push("target_systems is empty".to_string()),
        Some(t) => {
            if t.iter().any(|s| s.is_empty()) {
                errors.push("target_systems contains an empty entry".to_string());
            }
        }
    }
    match &manifest.declared_identity {
        None => errors.push("declared_identity is missing".to_string()),
        Some(identity) => {
            let has_git = !blank(&identity.principal);
            let has_maf = !blank(&identity.provider) && !blank(&identity.model);
            if !has_git && !has_maf {
                errors.push(
                    "declared_identity needs a non-empty principal or provider+model".to_string(),
                );
            }
        }
    }
    match &manifest.capability_scope {
        None => errors.push("capability_scope is missing".to_string()),
        Some(caps) if caps.is_empty() => {
            errors.push("capability_scope is empty".to_string());
        }
        Some(caps) => {
            for (i, cap) in caps.iter().enumerate() {
                validate_unified_capability(i, cap, &mut errors);
            }
        }
    }
    if errors.is_empty() {
        Ok(manifest)
    } else {
        Err(errors.join("; "))
    }
}

/// Validates one unified capability item against its schema variant
/// (git action / invoke_tool / handoff), appending field-naming errors.
fn validate_unified_capability(i: usize, cap: &UnifiedCapability, errors: &mut Vec<String>) {
    match cap.action.as_deref() {
        None | Some("") => {
            errors.push(format!("capability_scope[{i}].action is missing or empty"));
        }
        Some("invoke_tool") => {
            if blank(&cap.tool_kind) {
                errors.push(format!(
                    "capability_scope[{i}] (invoke_tool) is missing tool_kind"
                ));
            }
            if blank(&cap.target) {
                errors.push(format!(
                    "capability_scope[{i}] (invoke_tool) is missing target"
                ));
            }
            if blank(&cap.approval) {
                errors.push(format!(
                    "capability_scope[{i}] (invoke_tool) is missing approval"
                ));
            }
        }
        Some("handoff") => {
            if blank(&cap.target) {
                errors.push(format!("capability_scope[{i}] (handoff) is missing target"));
            }
        }
        Some(action) => {
            // Git action variant: the action must be a schema-known git
            // action, and mode + non-empty resources are required.
            if !KNOWN_GIT_ACTIONS.contains(&action) {
                errors.push(format!(
                    "capability_scope[{i}].action '{action}' is not a known git action"
                ));
            }
            if blank(&cap.mode) {
                errors.push(format!("capability_scope[{i}] (git) is missing mode"));
            }
            if cap.resources.as_ref().map(Vec::is_empty).unwrap_or(true) {
                errors.push(format!(
                    "capability_scope[{i}] (git) is missing or has empty resources"
                ));
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::test_support::corpus_path;

    #[test]
    fn parses_the_gh_pr_bot_repo_passport() {
        let raw = std::fs::read_to_string(corpus_path(
            "repos/gh-pr-bot/repo/.inspect_ia_agents/manifest.json",
        ))
        .expect("read");
        let m = Passport::parse(&raw).expect("valid passport");
        assert_eq!(m.principal(), "acme-dependency-pr-bot[bot]");
        assert_eq!(m.target_system(), "github");
        // Repo shape: single target wrapped in a one-element vec, no agent_id.
        assert_eq!(m.target_systems(), vec!["github".to_string()]);
        assert_eq!(m.agent_id(), None);
        assert_eq!(
            m.actions(),
            vec!["open_pr".to_string(), "read_repo".to_string()]
        ); // sorted
        assert_eq!(m.kind(), "git_agent");
        assert!(m.handoffs().is_empty());
    }

    #[test]
    fn invalid_json_yields_invalid_with_errors() {
        let err = Passport::parse("{not json").unwrap_err();
        assert!(matches!(err, PassportError::InvalidJson(_)));
        assert!(
            err.to_string().starts_with("invalid JSON:"),
            "unexpected Display: {err}"
        );
    }

    #[test]
    fn structurally_wrong_manifest_reports_missing_fields() {
        // Present file, wrong shape: missing identity, target_system and
        // capabilities -- the error must name all three fields.
        let err = Passport::parse(r#"{"schema_version":"1.0","agent":{"name":"x"}}"#).unwrap_err();
        let msg = err.to_string();
        assert!(msg.contains("identity"), "missing identity in: {msg}");
        assert!(
            msg.contains("target_system"),
            "missing target_system in: {msg}"
        );
        assert!(
            msg.contains("capabilities"),
            "missing capabilities in: {msg}"
        );
    }

    #[test]
    fn parses_the_unified_git_agent_manifest() {
        let raw =
            std::fs::read_to_string(corpus_path("agents/correct/gh-issue-triager/manifest.json"))
                .expect("read");
        let m = Passport::parse(&raw).expect("valid passport");
        // Unified shape without an explicit `kind` defaults to git_agent
        // (backward compatibility, per agent-manifest.schema.json).
        assert_eq!(m.kind(), "git_agent");
        assert_eq!(m.principal(), "acme-issue-triager[bot]");
        assert_eq!(m.target_system(), "github");
        assert_eq!(m.target_systems(), vec!["github".to_string()]);
        assert_eq!(m.agent_id(), Some("gh-issue-triager"));
        assert_eq!(
            m.actions(),
            vec![
                "comment_issue".to_string(),
                "list_repos".to_string(),
                "open_issue".to_string(),
                "read_repo".to_string(),
            ]
        );
        assert!(m.handoffs().is_empty());
    }

    #[test]
    fn parses_the_maf_agent_manifest_and_exposes_handoffs() {
        let raw = std::fs::read_to_string(corpus_path(
            "maf_agents/correct/diagnostic-correct/spec.json",
        ))
        .expect("read");
        let m = Passport::parse(&raw).expect("valid passport");
        assert_eq!(m.kind(), "maf_agent");
        // MAF identity has no principal; the composed provider:model stands in.
        assert_eq!(m.principal(), "AzureOpenAI:=Env.MODEL");
        // target_system() is the first of the sorted target_systems:
        // sorted(["azureopenai", "web_search", "mcp"])[0] == "azureopenai".
        assert_eq!(m.target_system(), "azureopenai");
        assert_eq!(
            m.target_systems(),
            vec![
                "azureopenai".to_string(),
                "mcp".to_string(),
                "web_search".to_string(),
            ]
        );
        assert_eq!(m.agent_id(), Some("diagnostic-correct"));
        assert_eq!(
            m.actions(),
            vec!["handoff".to_string(), "invoke_tool".to_string()]
        );
        assert_eq!(m.handoffs(), vec!["remediation-agent".to_string()]);
    }

    #[test]
    fn unified_manifest_with_empty_capability_scope_names_the_field() {
        let raw = r#"{
            "agent_id": "x-agent",
            "name": "x",
            "target_systems": ["github"],
            "declared_identity": {"auth_method": "pat", "principal": "x-bot"},
            "capability_scope": [],
            "runtime": {"lab_mode": true, "real_mode": false},
            "version": "1.0.0"
        }"#;
        let err = Passport::parse(raw).unwrap_err();
        assert!(err.to_string().contains("capability_scope"));
    }

    #[test]
    fn unified_manifest_with_typo_git_action_names_index_and_action() {
        // "raed_repo" is not in the schema enum (KNOWN_GIT_ACTIONS).
        let raw = r#"{
            "agent_id": "x-agent",
            "name": "x",
            "target_systems": ["github"],
            "declared_identity": {"auth_method": "pat", "principal": "x-bot"},
            "capability_scope": [
                {"action": "raed_repo", "mode": "read", "resources": ["acme/*"]}
            ],
            "runtime": {"lab_mode": true, "real_mode": false},
            "version": "1.0.0"
        }"#;
        let err = Passport::parse(raw).unwrap_err();
        let msg = err.to_string();
        assert!(
            msg.contains("capability_scope[0].action 'raed_repo' is not a known git action"),
            "missing enum-guard error in: {msg}"
        );
    }

    #[test]
    fn repo_manifest_with_empty_principal_names_the_field() {
        let raw = r#"{
            "schema_version": "1.0",
            "agent": {
                "name": "x",
                "target_system": "github",
                "identity": {"auth_method": "pat", "principal": ""},
                "capabilities": [
                    {"action": "read_repo", "mode": "read", "resources": ["acme/*"]}
                ]
            }
        }"#;
        let err = Passport::parse(raw).unwrap_err();
        assert!(err.to_string().contains("principal"));
    }

    #[test]
    fn shape_mismatch_reports_both_shape_errors() {
        // Neither repo shape (no `agent`) nor unified shape (no `agent_id`).
        let err = Passport::parse(r#"{"foo": 1}"#).unwrap_err();
        let msg = err.to_string();
        assert!(msg.contains("repo shape"), "missing repo error: {msg}");
        assert!(
            msg.contains("unified shape"),
            "missing unified error: {msg}"
        );
    }
}
