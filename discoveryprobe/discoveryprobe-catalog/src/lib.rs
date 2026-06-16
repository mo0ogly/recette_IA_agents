//! Declarative agent-catalog registry ingestion for the Rust discovery engine.
//!
//! A discovery/registry source can publish a machine-readable index of agents: a
//! `version` plus a list of entries, each DECLARING an agent's identity
//! (`name` / `version` / `publisher_name`), purpose (`description` / `tags`) and
//! the tools it is associated with (`associated_tools` / `foundry_tools`). This
//! crate parses that index and projects it onto the INVARIANT discovery
//! properties the recette judges -- agent count, name de-duplication, tool
//! coverage, the tag set -- never opaque values (R20: discovery ground-truth is
//! invariant-only, never a `canonical_agent_id` or an exact score).
//!
//! The shape here is the field contract of the public declarative-catalog
//! format; the crate carries only that contract and is exercised with the
//! recette's own fixtures, no third-party catalog data.
//!
//! Determinism (I4): parsing + projection are pure functions of the input JSON;
//! the summary sorts and de-duplicates, so the same registry yields a
//! byte-stable [`DiscoverySummary`]. `generated_at` is operational metadata and
//! never enters the projection.

#![deny(missing_docs)]

use std::collections::BTreeSet;

use serde::{Deserialize, Serialize};

/// An error parsing a catalog registry index.
#[derive(Debug, thiserror::Error)]
pub enum CatalogError {
    /// The registry JSON was malformed or did not match the expected shape.
    #[error("invalid catalog registry JSON: {0}")]
    Json(#[from] serde_json::Error),
}

/// One agent entry in the catalog registry index.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CatalogEntry {
    /// Agent slug identifier.
    pub name: String,
    /// Entry type discriminator (e.g. `"agent"`).
    #[serde(rename = "type", default)]
    pub entry_type: Option<String>,
    /// Catalog-relative path of the entry (informational).
    #[serde(default)]
    pub path: Option<String>,
    /// Semantic version of the agent.
    pub version: String,
    /// Publishing party name.
    #[serde(default)]
    pub publisher_name: Option<String>,
    /// One-paragraph functional description.
    #[serde(default)]
    pub description: Option<String>,
    /// Categorical labels.
    #[serde(default)]
    pub tags: Vec<String>,
    /// Paths to the agent's associated tool definitions.
    #[serde(default)]
    pub associated_tools: Vec<String>,
    /// Hosted/managed tool references.
    #[serde(default)]
    pub foundry_tools: Vec<String>,
    /// Regions the agent is offered in.
    #[serde(default)]
    pub supported_regions: Vec<String>,
}

impl CatalogEntry {
    /// Whether the entry declares at least one tool (associated or hosted) --
    /// the capability-coverage signal for discovery.
    pub fn has_tools(&self) -> bool {
        !self.associated_tools.is_empty() || !self.foundry_tools.is_empty()
    }

    /// Total declared tool count (associated + hosted).
    pub fn tool_count(&self) -> usize {
        self.associated_tools.len() + self.foundry_tools.len()
    }
}

/// A parsed catalog registry index.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CatalogRegistry {
    /// Registry format version.
    pub version: String,
    /// When the index was generated -- operational metadata, kept off the
    /// projection (I4).
    #[serde(default)]
    pub generated_at: Option<String>,
    /// The agent entries.
    pub entries: Vec<CatalogEntry>,
}

impl CatalogRegistry {
    /// Parse a registry from its JSON index.
    pub fn from_json(raw: &str) -> Result<Self, CatalogError> {
        Ok(serde_json::from_str(raw)?)
    }

    /// Total number of entries (including any duplicates).
    pub fn len(&self) -> usize {
        self.entries.len()
    }

    /// Whether the registry has no entries.
    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    /// The set of distinct agent names, sorted and de-duplicated -- the
    /// detection / dedup invariant.
    pub fn unique_names(&self) -> BTreeSet<&str> {
        self.entries.iter().map(|e| e.name.as_str()).collect()
    }

    /// Whether any agent name appears more than once.
    pub fn has_duplicate_names(&self) -> bool {
        self.unique_names().len() != self.entries.len()
    }

    /// Number of entries declaring at least one tool (the coverage invariant).
    pub fn with_tools(&self) -> usize {
        self.entries.iter().filter(|e| e.has_tools()).count()
    }

    /// All tags across the registry, sorted and de-duplicated.
    pub fn all_tags(&self) -> BTreeSet<&str> {
        self.entries
            .iter()
            .flat_map(|e| e.tags.iter().map(String::as_str))
            .collect()
    }

    /// Look up an entry by agent name.
    pub fn entry(&self, name: &str) -> Option<&CatalogEntry> {
        self.entries.iter().find(|e| e.name == name)
    }

    /// Project the registry onto the invariant discovery summary.
    pub fn summary(&self) -> DiscoverySummary {
        DiscoverySummary {
            total: self.len(),
            unique: self.unique_names().len(),
            with_tools: self.with_tools(),
            tags: self.all_tags().into_iter().map(str::to_string).collect(),
        }
    }
}

/// The invariant-only projection of a catalog registry for discovery scoring.
///
/// Deterministic (sorted, de-duplicated tags) and free of opaque values -- it
/// carries the properties the discovery recette is allowed to assert (count,
/// dedup, tool coverage, tags), never a `canonical_agent_id` or an exact score
/// (R20).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DiscoverySummary {
    /// Total entry count.
    pub total: usize,
    /// Number of distinct agent names.
    pub unique: usize,
    /// Number of entries declaring at least one tool.
    pub with_tools: usize,
    /// Sorted, de-duplicated tag set.
    pub tags: Vec<String>,
}

#[cfg(test)]
mod tests {
    use super::*;

    // The recette's OWN catalog fixture, in the declarative-catalog format
    // (our test agents, no third-party data): two tool-bearing agents and one
    // silent agent declaring nothing.
    const SAMPLE: &str = r#"{
      "version": "1.0",
      "generated_at": null,
      "entries": [
        {"name": "gh-pr-bot", "type": "agent", "path": "agents/gh-pr-bot",
         "version": "1.0.0", "publisher_name": "recette",
         "description": "opens pull requests", "tags": ["github", "pr-bot"],
         "associated_tools": ["tools/open_pr"]},
        {"name": "okta-provisioner", "type": "agent", "version": "2.1.0",
         "publisher_name": "recette", "description": "provisions identities",
         "tags": ["identity", "okta"], "associated_tools": ["tools/provision"],
         "foundry_tools": ["hosted/audit"]},
        {"name": "silent-scanner", "type": "agent", "version": "0.1.0",
         "tags": [], "associated_tools": []}
      ]
    }"#;

    fn registry() -> CatalogRegistry {
        CatalogRegistry::from_json(SAMPLE).expect("parse sample registry")
    }

    #[test]
    fn parses_all_entries_with_their_fields() {
        let reg = registry();
        assert_eq!(reg.version, "1.0");
        assert_eq!(reg.len(), 3);
        let bot = reg.entry("gh-pr-bot").expect("gh-pr-bot present");
        assert_eq!(bot.version, "1.0.0");
        assert_eq!(bot.publisher_name.as_deref(), Some("recette"));
        assert_eq!(bot.associated_tools, vec!["tools/open_pr".to_string()]);
    }

    #[test]
    fn unique_names_deduplicate_and_sort() {
        let reg = registry();
        let names: Vec<&str> = reg.unique_names().into_iter().collect();
        assert_eq!(
            names,
            vec!["gh-pr-bot", "okta-provisioner", "silent-scanner"]
        );
        assert!(!reg.has_duplicate_names());
    }

    #[test]
    fn duplicate_name_is_detected() {
        let raw = r#"{"version":"1.0","entries":[
            {"name":"dup","version":"1.0.0"},
            {"name":"dup","version":"2.0.0"}
        ]}"#;
        let reg = CatalogRegistry::from_json(raw).expect("parse");
        assert!(reg.has_duplicate_names());
        assert_eq!(reg.unique_names().len(), 1);
        assert_eq!(reg.len(), 2);
    }

    #[test]
    fn tool_coverage_counts_associated_and_hosted() {
        let reg = registry();
        // gh-pr-bot (associated) + okta-provisioner (associated + hosted) = 2;
        // silent-scanner declares none.
        assert_eq!(reg.with_tools(), 2);
        assert_eq!(reg.entry("okta-provisioner").unwrap().tool_count(), 2);
        assert!(!reg.entry("silent-scanner").unwrap().has_tools());
    }

    #[test]
    fn all_tags_are_sorted_and_deduplicated() {
        let reg = registry();
        let tags: Vec<&str> = reg.all_tags().into_iter().collect();
        assert_eq!(tags, vec!["github", "identity", "okta", "pr-bot"]);
    }

    #[test]
    fn summary_is_invariant_only_and_deterministic() {
        let reg = registry();
        let a = reg.summary();
        let b = registry().summary();
        assert_eq!(a, b); // deterministic
        assert_eq!(a.total, 3);
        assert_eq!(a.unique, 3);
        assert_eq!(a.with_tools, 2);
        assert_eq!(a.tags, vec!["github", "identity", "okta", "pr-bot"]);
    }

    #[test]
    fn missing_optional_fields_default_gracefully() {
        let raw = r#"{"version":"1.0","entries":[{"name":"bare","version":"1.0.0"}]}"#;
        let reg = CatalogRegistry::from_json(raw).expect("parse");
        let bare = reg.entry("bare").unwrap();
        assert!(bare.tags.is_empty());
        assert!(bare.associated_tools.is_empty());
        assert_eq!(bare.entry_type, None);
        assert!(!bare.has_tools());
    }

    #[test]
    fn malformed_json_is_an_error_not_a_panic() {
        assert!(CatalogRegistry::from_json("{not json").is_err());
    }
}
