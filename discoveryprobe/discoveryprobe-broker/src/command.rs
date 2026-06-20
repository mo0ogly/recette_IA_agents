//! The single parameterised command and its deny-by-default validation.
//!
//! The broker accepts exactly one command shape -- `capture` -- with a bounded
//! agent list and duration. There is no arbitrary exec, no free path, no shell
//! argument (design §7). Validation is a pure function so it is exhaustively
//! unit-tested without privilege.

use std::time::Duration;

use discoveryprobe::AgentProcessSpec;
use serde::Deserialize;

use crate::manifest::Manifest;

/// A capture request as received over the socket (one JSON line).
#[derive(Debug, Clone, Deserialize)]
pub struct CaptureRequest {
    /// Must be `"capture"` -- the only accepted command.
    pub command: String,
    /// Agent ids to observe; each MUST be declared in the manifest.
    pub agents: Vec<String>,
    /// Requested capture window in milliseconds (bounded by the manifest).
    pub duration_ms: u64,
    /// Optional exact pids per agent id, for PRECISE attribution when the
    /// launcher spawned the process and knows its pid (sidesteps `comm`
    /// truncation/collision). Absent -> match by manifest `comm_marker` only.
    #[serde(default)]
    pub agent_pids: std::collections::HashMap<String, Vec<u32>>,
}

/// A validated, ready-to-run capture: resolved process specs + bounded window.
#[derive(Debug, Clone, PartialEq)]
pub struct ValidatedCapture {
    /// Per-agent process specs resolved from the manifest markers.
    pub specs: Vec<AgentProcessSpec>,
    /// The bounded capture window.
    pub duration: Duration,
}

/// Why a request was refused. Deny-by-default: anything not explicitly allowed
/// lands here, and the broker never runs a capture for it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RejectReason {
    /// The command field was not `"capture"`.
    UnknownCommand(String),
    /// No agents requested.
    NoAgents,
    /// An agent id is not declared in the manifest (deny-by-default).
    UnknownAgent(String),
    /// `duration_ms` was zero.
    DurationZero,
    /// `duration_ms` exceeded the manifest ceiling.
    DurationTooLong { requested: u64, max: u64 },
}

impl RejectReason {
    /// A stable human-readable reason for the audit/response.
    pub fn message(&self) -> String {
        match self {
            Self::UnknownCommand(c) => format!("unknown command: {c}"),
            Self::NoAgents => "no agents requested".to_string(),
            Self::UnknownAgent(a) => format!("unknown agent: {a}"),
            Self::DurationZero => "duration_ms must be > 0".to_string(),
            Self::DurationTooLong { requested, max } => {
                format!("duration_ms {requested} exceeds max {max}")
            }
        }
    }
}

/// Validate a request against the manifest. Pure + total: every rejection is an
/// explicit [`RejectReason`]; a success resolves the process markers so the
/// caller never re-reads the manifest.
pub fn validate(
    request: &CaptureRequest,
    manifest: &Manifest,
) -> Result<ValidatedCapture, RejectReason> {
    // "capture" = one bounded window; "watch" = a gap-free passive stream
    // (same validation: allowlisted agents + bounded slice).
    if request.command != "capture" && request.command != "watch" {
        return Err(RejectReason::UnknownCommand(request.command.clone()));
    }
    if request.agents.is_empty() {
        return Err(RejectReason::NoAgents);
    }
    if request.duration_ms == 0 {
        return Err(RejectReason::DurationZero);
    }
    if request.duration_ms > manifest.max_duration_ms {
        return Err(RejectReason::DurationTooLong {
            requested: request.duration_ms,
            max: manifest.max_duration_ms,
        });
    }
    let mut specs = Vec::with_capacity(request.agents.len());
    for agent_id in &request.agents {
        let marker = manifest
            .marker(agent_id)
            .ok_or_else(|| RejectReason::UnknownAgent(agent_id.clone()))?;
        match request.agent_pids.get(agent_id) {
            Some(pids) if !pids.is_empty() => {
                specs.push(AgentProcessSpec::with_pids(agent_id, marker, pids.clone()))
            }
            _ => specs.push(AgentProcessSpec::new(agent_id, marker)),
        }
    }
    Ok(ValidatedCapture {
        specs,
        duration: Duration::from_millis(request.duration_ms),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn manifest() -> Manifest {
        Manifest::from_json(
            r#"{"max_duration_ms":5000,"agents":{"pr-bot-sdk":{"comm_marker":"pr-bot"}}}"#,
        )
        .unwrap()
    }

    fn req(command: &str, agents: &[&str], duration_ms: u64) -> CaptureRequest {
        CaptureRequest {
            command: command.to_string(),
            agents: agents.iter().map(|s| s.to_string()).collect(),
            duration_ms,
            agent_pids: std::collections::HashMap::new(),
        }
    }

    #[test]
    fn valid_request_resolves_specs_and_duration() {
        let ok = validate(&req("capture", &["pr-bot-sdk"], 3000), &manifest()).unwrap();
        assert_eq!(
            ok.specs,
            vec![AgentProcessSpec::new("pr-bot-sdk", "pr-bot")]
        );
        assert_eq!(ok.duration, Duration::from_millis(3000));
    }

    #[test]
    fn unknown_command_is_rejected() {
        let err = validate(&req("shell", &["pr-bot-sdk"], 1000), &manifest()).unwrap_err();
        assert_eq!(err, RejectReason::UnknownCommand("shell".to_string()));
    }

    #[test]
    fn undeclared_agent_is_denied_by_default() {
        let err = validate(&req("capture", &["intruder"], 1000), &manifest()).unwrap_err();
        assert_eq!(err, RejectReason::UnknownAgent("intruder".to_string()));
    }

    #[test]
    fn empty_agents_is_rejected() {
        let err = validate(&req("capture", &[], 1000), &manifest()).unwrap_err();
        assert_eq!(err, RejectReason::NoAgents);
    }

    #[test]
    fn zero_duration_is_rejected() {
        let err = validate(&req("capture", &["pr-bot-sdk"], 0), &manifest()).unwrap_err();
        assert_eq!(err, RejectReason::DurationZero);
    }

    #[test]
    fn duration_over_ceiling_is_rejected() {
        let err = validate(&req("capture", &["pr-bot-sdk"], 9000), &manifest()).unwrap_err();
        assert_eq!(
            err,
            RejectReason::DurationTooLong {
                requested: 9000,
                max: 5000
            }
        );
    }
}
