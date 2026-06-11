//! Report rendering: text (default) and JSON.

use std::path::Path;

use anyhow::{Context, Result};
use clap::ValueEnum;
use serde::Serialize;

use crate::model::{CheckResult, Verdict};
use crate::scoring::ScoreReport;

/// Output format for the report.
#[derive(Debug, Clone, Copy, ValueEnum)]
pub enum OutputFormat {
    /// Human-readable text report.
    Text,
    /// Machine-readable JSON for CI / apex / pdca.
    Json,
}

#[derive(Serialize)]
struct JsonReport<'a> {
    target: String,
    checks: &'a [CheckResult],
    scoring: &'a ScoreReport,
}

/// Render the report in the requested format to stdout.
pub fn render(
    format: OutputFormat,
    target: &Path,
    results: &[CheckResult],
    scored: &ScoreReport,
) -> Result<()> {
    match format {
        OutputFormat::Json => render_json(target, results, scored),
        OutputFormat::Text => {
            render_text(target, results, scored);
            Ok(())
        }
    }
}

fn render_json(target: &Path, results: &[CheckResult], scored: &ScoreReport) -> Result<()> {
    let report = JsonReport {
        target: target.display().to_string(),
        checks: results,
        scoring: scored,
    };
    let json = serde_json::to_string_pretty(&report).context("serializing JSON report")?;
    println!("{json}");
    Ok(())
}

fn render_text(target: &Path, results: &[CheckResult], scored: &ScoreReport) {
    println!("RAPPORT RUST RECETTE - {}", target.display());
    println!("==========================================");

    for bloc in ['A', 'B', 'C', 'D', 'E', 'F'] {
        let in_bloc: Vec<&CheckResult> = results.iter().filter(|r| r.bloc == bloc).collect();
        if in_bloc.is_empty() {
            continue;
        }
        println!("\nBLOC {bloc}");
        println!("----");
        for r in in_bloc {
            let verdict = match r.verdict {
                Verdict::Pass => "PASS",
                Verdict::Fail => "FAIL",
                Verdict::Na => "N/A ",
            };
            let note = r
                .note
                .as_deref()
                .map(|n| format!("  ({n})"))
                .unwrap_or_default();
            println!("{:<4} {:<34} : {verdict}{note}", r.id, r.name);
            for f in r.findings.iter().take(5) {
                println!("       - {}:{}  {}", f.file, f.line, f.excerpt);
            }
            if r.findings.len() > 5 {
                println!("       ... {} more", r.findings.len() - 5);
            }
        }
    }

    println!("\n==========================================");
    for b in &scored.blocs {
        if b.applicable == 0 {
            println!("SCORE {} : N/A ({} checks, all manual/skipped)", b.bloc, 0);
        } else {
            println!(
                "SCORE {} : {:.1}/{:.0} ({}/{} checks pass)",
                b.bloc, b.score, b.max, b.passed, b.applicable
            );
        }
    }
    println!(
        "SCORE GLOBAL : {:.1}/{:.0}  (normalized {:.1}/44)",
        scored.global, scored.global_max, scored.normalized_44
    );
    println!(
        "CRITIQUES en FAIL : {} | Bloc E FAIL : {} | Bloc F viole : {}",
        scored.critical_fails, scored.e_fail, scored.f_violation
    );
    println!("VERDICT : {}", scored.verdict);
}
