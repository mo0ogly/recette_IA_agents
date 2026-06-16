//! discoveryprobe-broker binary -- the privileged capture daemon.
//!
//! Launched by ./recette.sh only (R19), with CAP_BPF. Parses its socket /
//! manifest / audit / bpf-object paths and serves capture requests.
//!
//! Usage:
//!   discoveryprobe-broker --socket <path> --manifest <path> \
//!       --audit <path> --bpf-object <path>

use std::path::PathBuf;

use anyhow::{bail, Context, Result};
use discoveryprobe_broker::{serve, ServerConfig};

fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .init();

    let config = parse_args()?;
    serve(&config)
}

fn parse_args() -> Result<ServerConfig> {
    let mut socket_path: Option<PathBuf> = None;
    let mut manifest_path: Option<PathBuf> = None;
    let mut audit_path: Option<PathBuf> = None;
    let mut bpf_object_path: Option<PathBuf> = None;

    let mut args = std::env::args().skip(1);
    while let Some(flag) = args.next() {
        match flag.as_str() {
            "--socket" => socket_path = Some(next_value(&mut args, &flag)?),
            "--manifest" => manifest_path = Some(next_value(&mut args, &flag)?),
            "--audit" => audit_path = Some(next_value(&mut args, &flag)?),
            "--bpf-object" => bpf_object_path = Some(next_value(&mut args, &flag)?),
            other => bail!("unknown argument: {other}"),
        }
    }

    Ok(ServerConfig {
        socket_path: socket_path.context("--socket is required")?,
        manifest_path: manifest_path.context("--manifest is required")?,
        audit_path: audit_path.context("--audit is required")?,
        bpf_object_path: bpf_object_path.context("--bpf-object is required")?,
    })
}

fn next_value(args: &mut impl Iterator<Item = String>, flag: &str) -> Result<PathBuf> {
    args.next()
        .map(PathBuf::from)
        .with_context(|| format!("missing value for {flag}"))
}
