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
use discoveryprobe::{
    capture, recordings_from_capture, AgentProcessSpec, Capture, CaptureConfig, Session,
};

use crate::audit::{sha256_hex, AuditLog};
use crate::command::{validate, CaptureRequest};
use crate::handler::{handle, BrokerResponse};
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
                    // `{:#}` so the full anyhow cause chain (e.g. the verifier /
                    // errno behind a BPF load failure) is logged, not just the
                    // top context.
                    tracing::warn!(error = format!("{error:#}"), "connection failed");
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

    // "watch" = a gap-free passive stream: attach once and emit a recording
    // line per slice over the SAME connection until the client disconnects.
    if request.command == "watch" {
        return handle_watch(stream, &request, manifest, config);
    }

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

/// Gap-free passive stream: attach the eBPF probe ONCE and emit one recording
/// JSON line per slice over the connection until the client disconnects. Unlike
/// repeated `capture` (which re-attaches each window, missing events between
/// them), the kernel ring stays attached, so nothing is lost between drains.
/// PRIVILEGED (CAP_BPF). A rejected request gets one `Rejected` line, then ends.
fn handle_watch(
    stream: UnixStream,
    request: &CaptureRequest,
    manifest: &Manifest,
    config: &ServerConfig,
) -> Result<()> {
    let mut writer = stream;
    let validated = match validate(request, manifest) {
        Ok(v) => v,
        Err(reason) => {
            let resp = BrokerResponse::Rejected {
                reason: reason.message(),
            };
            writeln!(writer, "{}", serde_json::to_string(&resp)?).context("write rejected")?;
            return Ok(());
        }
    };
    let mut session = match Session::attach(&config.bpf_object_path) {
        Ok(s) => s,
        Err(error) => {
            let resp = BrokerResponse::Rejected {
                reason: format!("attach failed: {error:#}"),
            };
            writeln!(writer, "{}", serde_json::to_string(&resp)?).context("write attach error")?;
            return Ok(());
        }
    };
    // The validated duration is the drain interval (slice) of the stream.
    let slice = validated.duration;
    loop {
        std::thread::sleep(slice);
        let captured = session.drain();
        let recordings =
            recordings_from_capture(&validated.specs, &captured.execs, &captured.connects);
        let recordings_json = serde_json::to_string(&recordings)?;
        let resp = BrokerResponse::Ok {
            recordings,
            recording_sha256: sha256_hex(recordings_json.as_bytes()),
        };
        // A write error means the client closed the stream -> stop cleanly.
        if writeln!(writer, "{}", serde_json::to_string(&resp)?).is_err() || writer.flush().is_err()
        {
            break;
        }
    }
    Ok(())
}
