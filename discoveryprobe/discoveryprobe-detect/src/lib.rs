//! Static "reperage" of agent-observability tooling in a source.
//!
//! Given the text of a source file, [`detect`] reports which agent/LLM
//! observability tools it uses, by matching a bundled signature table of PUBLIC
//! identifiers -- package names, import paths, environment variables, and call
//! markers. Each tool is tagged with its [`Category`] (tracing / replay / audit
//! / eval / gateway). This is the DISCOVERY side: it scans static source, not a
//! running agent.
//!
//! The signature table is the recette's OWN data: public, matchable strings
//! (e.g. a package name or an env-var key), never third-party repository
//! content. Verified at the source before being recorded here.
//!
//! Determinism (I4): [`detect`] is a pure function of its input -- one match per
//! tool (the first needle that hits), results sorted by tool name -- so the same
//! source yields a byte-stable report.

#![deny(missing_docs)]

use serde::{Deserialize, Serialize};

/// What an observability tool primarily does.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Category {
    /// Captures spans/traces of LLM calls and agent steps.
    Tracing,
    /// Re-runs a recorded session.
    Replay,
    /// Immutable / tamper-evident audit log.
    Audit,
    /// Scores agent/LLM outputs.
    Eval,
    /// Proxies LLM traffic.
    Gateway,
}

/// One tool's signature: the identifiers that reveal its presence in a source.
#[derive(Debug, Clone, Copy)]
pub struct ObservabilitySignature {
    /// The tool's display name.
    pub tool: &'static str,
    /// Its primary category.
    pub category: Category,
    /// Distinctive public identifiers (package, import, env var, call marker);
    /// any one present in the source flags the tool.
    pub needles: &'static [&'static str],
}

/// The bundled signature table (the recette's own data; public identifiers).
///
/// Distinctive needles are chosen per tool to avoid cross-tool collisions (e.g.
/// the generic `@observe` decorator is shared by several tools, so a tool's
/// package name and env-var key are preferred).
static SIGNATURES: &[ObservabilitySignature] = &[
    ObservabilitySignature {
        tool: "Langfuse",
        category: Category::Tracing,
        needles: &["langfuse", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"],
    },
    ObservabilitySignature {
        tool: "LangSmith",
        category: Category::Tracing,
        needles: &["langsmith", "LANGSMITH_API_KEY", "LANGSMITH_TRACING"],
    },
    ObservabilitySignature {
        tool: "Traceloop/OpenLLMetry",
        category: Category::Tracing,
        needles: &["traceloop", "TRACELOOP_API_KEY", "Traceloop.init"],
    },
    ObservabilitySignature {
        tool: "Arize Phoenix",
        category: Category::Tracing,
        needles: &[
            "arize-phoenix",
            "phoenix.otel",
            "PHOENIX_API_KEY",
            "PHOENIX_COLLECTOR_ENDPOINT",
        ],
    },
    ObservabilitySignature {
        tool: "OpenInference",
        category: Category::Tracing,
        needles: &["openinference", "@arizeai/openinference"],
    },
    ObservabilitySignature {
        tool: "AgentOps",
        category: Category::Tracing,
        needles: &["agentops", "AGENTOPS_API_KEY"],
    },
    ObservabilitySignature {
        tool: "Helicone",
        category: Category::Gateway,
        needles: &["helicone", "HELICONE_API_KEY", "HeliconeManualLogger"],
    },
    ObservabilitySignature {
        tool: "Laminar",
        category: Category::Tracing,
        needles: &["lmnr", "LMNR_PROJECT_API_KEY", "Laminar.initialize"],
    },
    ObservabilitySignature {
        tool: "Braintrust",
        category: Category::Eval,
        needles: &["braintrust", "BRAINTRUST_API_KEY"],
    },
    ObservabilitySignature {
        tool: "Literal AI",
        category: Category::Tracing,
        needles: &["literalai", "LITERAL_API_KEY", "LiteralClient"],
    },
    ObservabilitySignature {
        tool: "HoneyHive",
        category: Category::Tracing,
        needles: &["honeyhive", "HoneyHiveTracer", "HH_API_KEY"],
    },
    ObservabilitySignature {
        tool: "OpenTelemetry GenAI",
        category: Category::Tracing,
        needles: &[
            "opentelemetry-instrumentation-openai-v2",
            "opentelemetry-util-genai",
            "OTEL_INSTRUMENTATION_GENAI",
        ],
    },
];

/// The bundled signature table.
pub fn signatures() -> &'static [ObservabilitySignature] {
    SIGNATURES
}

/// One detection: a tool found in the source, with the needle that revealed it.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ToolMatch {
    /// The detected tool's name.
    pub tool: String,
    /// Its category.
    pub category: Category,
    /// The first signature needle that matched (the evidence).
    pub matched: String,
}

/// Detect the observability tools present in `text`.
///
/// One match per tool (the first needle that hits), sorted by tool name --
/// pure and deterministic (I4). An empty result means no known tool was found.
pub fn detect(text: &str) -> Vec<ToolMatch> {
    let mut matches: Vec<ToolMatch> = SIGNATURES
        .iter()
        .filter_map(|sig| {
            sig.needles
                .iter()
                .find(|needle| text.contains(**needle))
                .map(|needle| ToolMatch {
                    tool: sig.tool.to_string(),
                    category: sig.category,
                    matched: (*needle).to_string(),
                })
        })
        .collect();
    matches.sort_by(|a, b| a.tool.cmp(&b.tool));
    matches
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn detects_a_tool_by_its_import() {
        let hits = detect("from langfuse import observe\n");
        assert_eq!(hits.len(), 1);
        assert_eq!(hits[0].tool, "Langfuse");
        assert_eq!(hits[0].category, Category::Tracing);
        assert_eq!(hits[0].matched, "langfuse");
    }

    #[test]
    fn detects_a_tool_by_its_env_var() {
        let hits = detect("LANGSMITH_API_KEY=ls-xxxx\n");
        assert_eq!(hits.len(), 1);
        assert_eq!(hits[0].tool, "LangSmith");
        assert_eq!(hits[0].matched, "LANGSMITH_API_KEY");
    }

    #[test]
    fn categorises_a_gateway_distinctly() {
        let hits = detect("base_url = 'https://oai.helicone.ai'  # HELICONE_API_KEY");
        assert_eq!(hits.len(), 1);
        assert_eq!(hits[0].tool, "Helicone");
        assert_eq!(hits[0].category, Category::Gateway);
    }

    #[test]
    fn clean_source_detects_nothing() {
        assert!(detect("def main():\n    print('hello')\n").is_empty());
    }

    #[test]
    fn multiple_tools_are_sorted_and_deduplicated() {
        let text = "import langfuse\nfrom braintrust import Eval\nlangfuse.get_client()";
        let hits = detect(text);
        // Langfuse appears twice in the text but is reported once; sorted by name.
        assert_eq!(hits.len(), 2);
        assert_eq!(hits[0].tool, "Braintrust");
        assert_eq!(hits[1].tool, "Langfuse");
        assert_eq!(hits[1].category, Category::Tracing);
    }

    #[test]
    fn detection_is_deterministic() {
        let text = "agentops.init()\nLMNR_PROJECT_API_KEY=x\nPHOENIX_API_KEY=y";
        assert_eq!(detect(text), detect(text));
    }

    #[test]
    fn the_table_covers_twelve_tools() {
        assert_eq!(signatures().len(), 12);
    }
}
