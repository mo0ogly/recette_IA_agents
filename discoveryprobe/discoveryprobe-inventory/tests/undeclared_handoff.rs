//! Integration test: an observed inter-agent edge that the declared team graph
//! does NOT contain must surface as a `Violation::UndeclaredHandoff` on the
//! source agent record AND in `comm_graph.undeclared_edges` (mono-axis: the
//! only violation on that agent is the undeclared handoff -- ASI07 / insecure
//! inter-agent communication modelled as a runtime-observed edge).
//!
//! Wiring (crate public API only):
//! - `DeclaredGraph::from_team_json` -> the declared mesh (intake -> wire ONLY).
//! - `serde_json` -> `ObservedInput` from the frozen `ipc_events.json`: a
//!   localhost connect (pid 100 = wire) paired with a listen (pid 200 = audit)
//!   yields exactly one derived edge wire -> audit, which is NOT declared.
//! - three scanned records (intake / wire / audit, valid MAF passports) so the
//!   `from` record ("wire") exists and the violation attaches to it.

use std::fs;
use std::path::PathBuf;

use discoveryprobe_inventory::correlate::correlate;
use discoveryprobe_inventory::graph::{DeclaredGraph, Edge};
use discoveryprobe_inventory::manifest::Passport;
use discoveryprobe_inventory::model::{Attestation, Conformity, ObservedInput, Violation};
use discoveryprobe_inventory::scan::{PassportStatus, ScannedAgent};

/// Resolves a committed fixture file under `tests/fixtures/undeclared-handoff/`.
fn fixture(rel: &str) -> String {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures/undeclared-handoff")
        .join(rel);
    fs::read_to_string(&path).unwrap_or_else(|e| panic!("read {}: {e}", path.display()))
}

/// Builds a scanned record carrying a VALID unified MAF passport whose
/// `agent_id` is `agent_id` and whose only capability is `capability`.
fn scanned_maf(agent_id: &str, capability: &str) -> ScannedAgent {
    let raw = format!(
        r#"{{
          "kind": "maf_agent",
          "agent_id": "{agent_id}",
          "name": "{agent_id}",
          "target_systems": ["AzureOpenAI"],
          "declared_identity": {{ "provider": "AzureOpenAI", "model": "gpt-4o" }},
          "capability_scope": [{capability}]
        }}"#
    );
    let passport = Passport::parse(&raw).expect("valid MAF passport");
    ScannedAgent {
        root: format!("tests/fixtures/undeclared-handoff/{agent_id}"),
        passport: PassportStatus::Present { passport },
        attestation: Attestation::Unsigned,
    }
}

#[test]
fn observed_wire_to_audit_edge_absent_from_team_json_is_an_undeclared_handoff() {
    // Declared mesh: intake -> wire ONLY (no wire -> audit edge).
    let declared = DeclaredGraph::from_team_json(&fixture("team.json")).expect("valid team.json");
    assert_eq!(
        declared.edges,
        vec![Edge {
            from: "intake".to_string(),
            to: "wire".to_string(),
        }],
        "team.json must declare exactly intake -> wire"
    );

    // Frozen observed IPC: one derived edge wire -> audit.
    let observed: ObservedInput =
        serde_json::from_str(&fixture("ipc_events.json")).expect("parse ObservedInput");

    // The three team participants scanned from source (valid passports).
    let scanned = vec![
        scanned_maf("intake", r#"{ "action": "handoff", "target": "wire" }"#),
        scanned_maf(
            "wire",
            r#"{ "action": "invoke_tool", "tool_kind": "mcp", "target": "https://mcp.example.com/finance/wire", "approval": "always" }"#,
        ),
        scanned_maf(
            "audit",
            r#"{ "action": "invoke_tool", "tool_kind": "web_search", "target": "web_search", "approval": "never" }"#,
        ),
    ];

    let inventory = correlate(&scanned, &declared, Some(&observed));

    let undeclared = Edge {
        from: "wire".to_string(),
        to: "audit".to_string(),
    };

    // 1. The comm graph lists exactly the one undeclared edge wire -> audit.
    assert_eq!(
        inventory.comm_graph.undeclared_edges,
        vec![undeclared.clone()],
        "undeclared_edges must list wire -> audit and nothing else"
    );
    assert_eq!(
        inventory.comm_graph.observed_edges,
        vec![undeclared.clone()],
        "observed_edges must be exactly the derived wire -> audit"
    );

    // 2. The violation attaches to the `from` record ("wire"), mono-axis: the
    //    ONLY violation there is the undeclared handoff.
    let wire = inventory
        .agents
        .iter()
        .find(|a| a.agent_id == "wire")
        .expect("wire record present");
    match &wire.conformity {
        Conformity::Violations { violations } => {
            assert_eq!(
                violations,
                &vec![Violation::UndeclaredHandoff {
                    from: "wire".to_string(),
                    to: "audit".to_string(),
                }],
                "wire must carry exactly one violation: the undeclared handoff"
            );
        }
        other => panic!("expected Violations on wire, got {other:?}"),
    }

    // 3. audit was observed (edge destination) with a valid declaration and no
    //    violation -> Conform; intake was never observed -> NotObserved.
    let audit = inventory
        .agents
        .iter()
        .find(|a| a.agent_id == "audit")
        .expect("audit record present");
    assert!(
        matches!(audit.conformity, Conformity::Conform),
        "audit should be Conform, got {:?}",
        audit.conformity
    );
    let intake = inventory
        .agents
        .iter()
        .find(|a| a.agent_id == "intake")
        .expect("intake record present");
    assert!(
        matches!(intake.conformity, Conformity::NotObserved),
        "intake should be NotObserved, got {:?}",
        intake.conformity
    );

    // Roll-up: one undeclared handoff, no other violation across the inventory.
    assert_eq!(inventory.summary.violation_count, 1);
}
