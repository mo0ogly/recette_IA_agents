//! The privileged Unix-socket server (CAP_BPF).
//!
//! Binds a local Unix socket with strict 0600 permissions, reads one JSON
//! `capture` request per connection, runs it through [`crate::handler::handle`]
//! with the REAL eBPF capture, and writes the JSON response back. The API relays
//! to this socket; the API never holds privilege (design §7). A bad connection
//! is logged and skipped -- it never kills the broker (failure-safe).
//!
//! This path requires CAP_BPF (it loads/attaches the eBPF program), so it runs
//! only under the broker process; the pure logic in `command`/`audit`/`handler`
//! is what the test suite covers.

use std::io::{BufRead, BufReader, Write};
use std::os::unix::fs::PermissionsExt;
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::PathBuf;
use std::time::Duration;

use anyhow::{Context, Result};
use discoveryprobe::{capture, AgentProcessSpec, Capture, CaptureConfig};

use crate::audit::AuditLog;
use crate::command::CaptureRequest;
use crate::handler::handle;
use crate::manifest::Manifest;

/// Where the broker listens and what it captures with.
#[derive(Debug, Clone)]
pub struct ServerConfig {
    /// Local Unix socket the API relays to (created 0600).
    pub socket_path: PathBuf,
    /// Declared-agents manifest (the allowlist + duration ceiling).
    pub manifest_path: PathBuf,
    /// Append-only audit log path (I1).
    pub audit_path: PathBuf,
    /// Path to the compiled eBPF object (`bpfel-unknown-none`).
    pub bpf_object_path: PathBuf,
}

/// Serve capture requests until the listener is closed. PRIVILEGED (CAP_BPF).
pub fn serve(config: &ServerConfig) -> Result<()> {
    let manifest = Manifest::load(&config.manifest_path)
        .with_context(|| format!("load manifest {}", config.manifest_path.display()))?;

    // Start from a fresh socket path; bind; then lock perms to owner-only.
    let _ = std::fs::remove_file(&config.socket_path);
    let listener = UnixListener::bind(&config.socket_path)
        .with_context(|| format!("bind {}", config.socket_path.display()))?;
    std::fs::set_permissions(&config.socket_path, std::fs::Permissions::from_mode(0o600))
        .context("set socket perms 0600")?;
    tracing::info!(socket = %config.socket_path.display(), "broker listening");

    for stream in listener.incoming() {
        match stream {
            Ok(stream) => {
                if let Err(error) = handle_conn(stream, &manifest, config) {
                    tracing::warn!(%error, "connection failed");
                }
            }
            Err(error) => tracing::warn!(%error, "accept failed"),
        }
    }
    Ok(())
}

fn handle_conn(stream: UnixStream, manifest: &Manifest, config: &ServerConfig) -> Result<()> {
    let mut reader = BufReader::new(stream.try_clone().context("clone stream")?);
    let mut line = String::new();
    reader.read_line(&mut line).context("read request")?;
    let request: CaptureRequest =
        serde_json::from_str(line.trim()).context("parse capture request")?;

    let mut audit = AuditLog::open(&config.audit_path);
    let object_path = config.bpf_object_path.clone();
    let response = handle(
        &request,
        manifest,
        &mut audit,
        move |_specs: &[AgentProcessSpec], window: Duration| -> Result<Capture> {
            // The eBPF programs capture every exec + connect; mapping filters by
            // marker and reconciles both onto the ebpf_wire surface.
            capture(&CaptureConfig {
                object_path,
                window,
            })
        },
    )?;

    let mut writer = stream;
    writeln!(writer, "{}", serde_json::to_string(&response)?).context("write response")?;
    Ok(())
}
