//! Append-only audit log (I1): every capture run is recorded immutably.
//!
//! One JSON object per line, opened in append mode and never rewritten. A run
//! emits a `capture_start` (parameters) and a `capture_end` (parameters + the
//! sha256 of the produced recording), so the audit is tamper-evident: the
//! recording hash binds the run to its result. Correction is a new record, never
//! a mutation (I1).

use std::io::Write;
use std::path::{Path, PathBuf};

use serde::Serialize;
use sha2::{Digest, Sha256};

/// One immutable audit record.
#[derive(Debug, Clone, Serialize)]
pub struct AuditRecord {
    /// `"capture_start"` or `"capture_end"`.
    pub event: String,
    /// Monotonic sequence within this log session (ordering, I4-friendly).
    pub seq: u64,
    /// The agents the run observed.
    pub agents: Vec<String>,
    /// The bounded capture window in milliseconds.
    pub duration_ms: u64,
    /// sha256 of the produced recording JSON; `None` on `capture_start`.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub recording_sha256: Option<String>,
}

/// An append-only audit sink. Holds the path and the next sequence number.
#[derive(Debug)]
pub struct AuditLog {
    path: PathBuf,
    seq: u64,
}

impl AuditLog {
    /// Open (creating if absent) an audit log in append mode. Existing content
    /// is never read back or rewritten -- the log is immutable (I1).
    pub fn open(path: impl AsRef<Path>) -> Self {
        Self {
            path: path.as_ref().to_path_buf(),
            seq: 0,
        }
    }

    /// Append one record as a JSON line. Append-only: opens with `append(true)`,
    /// never truncates. Returns the sequence number written.
    pub fn append(&mut self, record: &AuditRecord) -> anyhow::Result<u64> {
        let mut file = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.path)?;
        let line = serde_json::to_string(record)?;
        writeln!(file, "{line}")?;
        self.seq = record.seq.max(self.seq) + 1;
        Ok(record.seq)
    }

    /// The next sequence number to use.
    pub fn next_seq(&self) -> u64 {
        self.seq
    }
}

/// Lowercase-hex sha256 of `bytes` -- the recording integrity hash.
pub fn sha256_hex(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    let digest = hasher.finalize();
    let mut out = String::with_capacity(digest.len() * 2);
    for byte in digest {
        out.push_str(&format!("{byte:02x}"));
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sha256_hex_is_stable_and_known() {
        // Known vector: sha256("") = e3b0c442...
        assert_eq!(
            sha256_hex(b""),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        );
    }

    #[test]
    fn append_writes_one_line_per_record_in_order() {
        let dir = std::env::temp_dir().join(format!("dpb-audit-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("audit.jsonl");
        let _ = std::fs::remove_file(&path);
        let mut log = AuditLog::open(&path);
        log.append(&AuditRecord {
            event: "capture_start".to_string(),
            seq: 0,
            agents: vec!["pr-bot-sdk".to_string()],
            duration_ms: 3000,
            recording_sha256: None,
        })
        .unwrap();
        log.append(&AuditRecord {
            event: "capture_end".to_string(),
            seq: 1,
            agents: vec!["pr-bot-sdk".to_string()],
            duration_ms: 3000,
            recording_sha256: Some(sha256_hex(b"[]")),
        })
        .unwrap();
        let body = std::fs::read_to_string(&path).unwrap();
        let lines: Vec<&str> = body.lines().collect();
        assert_eq!(lines.len(), 2);
        assert!(lines[0].contains("capture_start"));
        assert!(lines[1].contains("capture_end"));
        // start record omits the hash field entirely.
        assert!(!lines[0].contains("recording_sha256"));
        assert!(lines[1].contains("recording_sha256"));
        let _ = std::fs::remove_file(&path);
    }
}
