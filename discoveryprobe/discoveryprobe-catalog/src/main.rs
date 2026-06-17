//! discoveryprobe-catalog CLI: summarise a declarative agent-catalog registry.
//!
//! Reads a registry index JSON and prints its INVARIANT discovery summary
//! (count, distinct names, tool coverage, sorted tags) -- the properties the
//! discovery recette is allowed to assert (R20). Usage:
//!   discoveryprobe-catalog <registry.json>

use std::process::ExitCode;

use discoveryprobe_catalog::CatalogRegistry;

fn main() -> ExitCode {
    let Some(path) = std::env::args().nth(1) else {
        eprintln!("usage: discoveryprobe-catalog <registry.json>");
        return ExitCode::FAILURE;
    };
    let raw = match std::fs::read_to_string(&path) {
        Ok(raw) => raw,
        Err(err) => {
            eprintln!("read {path}: {err}");
            return ExitCode::FAILURE;
        }
    };
    let registry = match CatalogRegistry::from_json(&raw) {
        Ok(registry) => registry,
        Err(err) => {
            eprintln!("parse {path}: {err}");
            return ExitCode::FAILURE;
        }
    };
    match serde_json::to_string_pretty(&registry.summary()) {
        Ok(json) => {
            println!("{json}");
            ExitCode::SUCCESS
        }
        Err(err) => {
            eprintln!("serialise summary: {err}");
            ExitCode::FAILURE
        }
    }
}
