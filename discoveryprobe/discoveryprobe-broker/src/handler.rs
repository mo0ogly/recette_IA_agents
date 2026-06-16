//! Orchestration: validate -> audit start -> capture -> recordings -> audit end.
//!
//! The capture step is INJECTED (a closure), so the whole flow -- validation,
//! auditing, hashing, response shaping -- is unit-tested with a stub capture,
//! without CAP_BPF. The real binary injects the privileged eBPF capture; tests
//! inject canned exec + connect events.

use std::time::Duration;

use discoveryprobe::{recordings_from_capture, AgentProcessSpec, Capture};
use discoveryprobe_core::CaptureRecording;
use serde::Serialize;

use crate::audit::{sha256_hex, AuditLog, AuditRecord};
use crate::command::{validate, CaptureRequest, RejectReason};
use crate::manifest::Manifest;

/// The broker's reply to one capture request.
#[derive(Debug, Clone, Serialize)]
#[serde(tag = "status", rename_all = "snake_case")]
pub enum BrokerResponse {
    /// The capture ran; recordings + their integrity hash.
    Ok {
        /// One recording per requested agent (the bridge to recette/surface).
        recordings: Vec<CaptureRecording>,
        /// sha256 of the recordings JSON (matches the audit `capture_end`).
        recording_sha256: String,
    },
    /// The request was refused before any capture (deny-by-default).
    Rejected {
        /// Stable human-readable reason.
        reason: String,
    },
}

/// Handle one capture request end-to-end.
///
/// `capture` is the (privileged, in the real binary) function that observes the
/// given process specs for the window and returns the captured kernel events
/// (execs + connects). A rejected request returns `BrokerResponse::Rejected`
/// and runs NO capture and writes NO audit (it was never a run). A validated
/// request audits start, runs the capture, builds normalised recordings
/// reconciling both surfaces, hashes them, audits end, and returns
/// `BrokerResponse::Ok`.
pub fn handle<F>(
    request: &CaptureRequest,
    manifest: &Manifest,
    audit: &mut AuditLog,
    capture: F,
) -> anyhow::Result<BrokerResponse>
where
    F: FnOnce(&[AgentProcessSpec], Duration) -> anyhow::Result<Capture>,
{
    let validated = match validate(request, manifest) {
        Ok(v) => v,
        Err(reason) => {
            return Ok(BrokerResponse::Rejected {
                reason: reason.message(),
            })
        }
    };

    let agents: Vec<String> = validated.specs.iter().map(|s| s.agent_id.clone()).collect();
    let duration_ms = validated.duration.as_millis() as u64;

    audit.append(&AuditRecord {
        event: "capture_start".to_string(),
        seq: audit.next_seq(),
        agents: agents.clone(),
        duration_ms,
        recording_sha256: None,
    })?;

    let captured = capture(&validated.specs, validated.duration)?;
    let recordings = recordings_from_capture(&validated.specs, &captured.execs, &captured.connects);
    let recordings_json = serde_json::to_string(&recordings)?;
    let recording_sha256 = sha256_hex(recordings_json.as_bytes());

    audit.append(&AuditRecord {
        event: "capture_end".to_string(),
        seq: audit.next_seq(),
        agents,
        duration_ms,
        recording_sha256: Some(recording_sha256.clone()),
    })?;

    Ok(BrokerResponse::Ok {
        recordings,
        recording_sha256,
    })
}

/// Refuse helper so callers can build a rejection without re-deriving the text.
pub fn rejected(reason: &RejectReason) -> BrokerResponse {
    BrokerResponse::Rejected {
        reason: reason.message(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use discoveryprobe_common::{ConnectEvent, ExecEvent};
    use discoveryprobe_core::ObservationSurface;

    fn manifest() -> Manifest {
        Manifest::from_json(
            r#"{"max_duration_ms":5000,"agents":{"pr-bot-sdk":{"comm_marker":"pr-bot"}}}"#,
        )
        .unwrap()
    }

    fn req(agents: &[&str], duration_ms: u64) -> CaptureRequest {
        CaptureRequest {
            command: "capture".to_string(),
            agents: agents.iter().map(|s| s.to_string()).collect(),
            duration_ms,
        }
    }

    fn comm_of(name: &str) -> [u8; discoveryprobe_common::COMM_LEN] {
        let mut comm = [0u8; discoveryprobe_common::COMM_LEN];
        let bytes = name.as_bytes();
        let n = bytes.len().min(discoveryprobe_common::COMM_LEN);
        comm[..n].copy_from_slice(&bytes[..n]);
        comm
    }

    fn exec(pid: u32, name: &str) -> ExecEvent {
        ExecEvent {
            pid,
            comm: comm_of(name),
        }
    }

    fn connect(pid: u32, daddr: [u8; 4], port: u16, name: &str) -> ConnectEvent {
        ConnectEvent {
            pid,
            daddr,
            dport: port.to_be_bytes(),
            _pad: [0u8; 2],
            comm: comm_of(name),
        }
    }

    fn audit_path(tag: &str) -> std::path::PathBuf {
        let p =
            std::env::temp_dir().join(format!("dpb-handler-{}-{tag}.jsonl", std::process::id()));
        let _ = std::fs::remove_file(&p);
        p
    }

    #[test]
    fn valid_capture_returns_recordings_and_audits_start_end() {
        let path = audit_path("ok");
        let mut audit = AuditLog::open(&path);
        let resp = handle(
            &req(&["pr-bot-sdk"], 3000),
            &manifest(),
            &mut audit,
            |specs, _| {
                assert_eq!(specs.len(), 1);
                Ok(Capture {
                    execs: vec![exec(42, "pr-bot")],
                    connects: vec![],
                })
            },
        )
        .unwrap();
        match resp {
            BrokerResponse::Ok {
                recordings,
                recording_sha256,
            } => {
                assert_eq!(recordings.len(), 1);
                assert_eq!(
                    recordings[0].surfaces.get(&ObservationSurface::EbpfWire),
                    Some(&vec!["exec:pr-bot:42".to_string()])
                );
                assert_eq!(recording_sha256.len(), 64);
            }
            other => panic!("expected Ok, got {other:?}"),
        }
        let body = std::fs::read_to_string(&path).unwrap();
        assert_eq!(body.lines().count(), 2);
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn rejected_request_runs_no_capture_and_writes_no_audit() {
        let path = audit_path("rej");
        let mut audit = AuditLog::open(&path);
        let mut capture_ran = false;
        let resp = handle(
            &req(&["intruder"], 3000),
            &manifest(),
            &mut audit,
            |_, _| {
                capture_ran = true;
                Ok(Capture::default())
            },
        )
        .unwrap();
        assert!(matches!(resp, BrokerResponse::Rejected { .. }));
        assert!(!capture_ran, "capture must not run for a denied request");
        assert!(!path.exists(), "no audit line for a non-run");
    }

    #[test]
    fn over_ceiling_duration_is_rejected() {
        let path = audit_path("dur");
        let mut audit = AuditLog::open(&path);
        let resp = handle(
            &req(&["pr-bot-sdk"], 9999),
            &manifest(),
            &mut audit,
            |_, _| Ok(Capture::default()),
        )
        .unwrap();
        match resp {
            BrokerResponse::Rejected { reason } => assert!(reason.contains("exceeds max")),
            other => panic!("expected Rejected, got {other:?}"),
        }
    }

    #[test]
    fn capture_reconciles_exec_and_connect_on_one_recording() {
        let path = audit_path("reconcile");
        let mut audit = AuditLog::open(&path);
        let resp = handle(
            &req(&["pr-bot-sdk"], 3000),
            &manifest(),
            &mut audit,
            |_, _| {
                Ok(Capture {
                    execs: vec![exec(42, "pr-bot")],
                    connects: vec![connect(42, [140, 82, 112, 3], 443, "pr-bot")],
                })
            },
        )
        .unwrap();
        match resp {
            BrokerResponse::Ok { recordings, .. } => {
                assert_eq!(
                    recordings[0].surfaces.get(&ObservationSurface::EbpfWire),
                    Some(&vec![
                        "connect:140.82.112.3:443".to_string(),
                        "exec:pr-bot:42".to_string()
                    ])
                );
            }
            other => panic!("expected Ok, got {other:?}"),
        }
        let _ = std::fs::remove_file(&path);
    }
}
