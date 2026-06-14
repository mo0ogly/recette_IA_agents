//! inspect_ia_agents_recette -- static recette scorer for inspect_ia_agents Rust code.
//!
//! Automates the pattern-based blocs (A/B/C/F) and shells out to the cargo
//! toolchain for the static-analysis bloc (D), producing a scored report
//! (text or JSON) plus a CI-friendly exit code. Rust counterpart of the Go
//! `lia_recette` CLI and the `/rust-recette` command.

mod model;
mod patterns;
mod report;
mod scan;
mod scoring;
mod tools;

use std::path::PathBuf;
use std::process::ExitCode;

use anyhow::{Context, Result};
use clap::Parser;

use crate::report::OutputFormat;

/// Command-line arguments.
#[derive(Parser, Debug)]
#[command(
    name = "inspect_ia_agents_recette",
    version,
    about = "Static recette scorer for inspect_ia_agents Rust code (blocs A-F + cargo SAST gate)"
)]
struct Cli {
    /// File or directory to audit (defaults to the current directory).
    #[arg(default_value = ".")]
    path: PathBuf,

    /// Output format.
    #[arg(long, value_enum, default_value = "text")]
    format: OutputFormat,

    /// Directory to run cargo tools from (defaults to the nearest crate of PATH).
    #[arg(long)]
    manifest_dir: Option<PathBuf>,

    /// Skip Bloc D (cargo clippy/audit/fmt/deny/geiger) for a fast pattern-only pass.
    #[arg(long)]
    skip_tools: bool,

    /// Minimum global score on the /44 scale required for exit code 0.
    #[arg(long, default_value_t = 39)]
    min_score: u32,
}

fn main() -> ExitCode {
    match run() {
        Ok(true) => ExitCode::SUCCESS,
        Ok(false) => ExitCode::FAILURE,
        Err(err) => {
            eprintln!("inspect_ia_agents_recette: {err:#}");
            ExitCode::FAILURE
        }
    }
}

/// Run the recette; returns `Ok(true)` when the gate passes.
fn run() -> Result<bool> {
    let cli = Cli::parse();

    let files = scan::collect_rs_files(&cli.path)
        .with_context(|| format!("scanning {}", cli.path.display()))?;

    let crate_dir = cli
        .manifest_dir
        .clone()
        .unwrap_or_else(|| scan::nearest_crate_dir(&cli.path));

    let mut results = patterns::run_all(&files, &crate_dir).context("running pattern checks")?;

    if cli.skip_tools {
        results.extend(tools::skipped_bloc_d());
    } else {
        results.extend(tools::run_all(&crate_dir));
    }

    let scored = scoring::score(&results);
    report::render(cli.format, &cli.path, &results, &scored).context("rendering report")?;

    Ok(scored.passes(cli.min_score))
}
