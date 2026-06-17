//! discoveryprobe-detect CLI: report the observability tools in a source file.
//!
//! Reads a source file and prints, as JSON, the observability tools detected in
//! it (tool, category, matched needle). Usage:
//!   discoveryprobe-detect <source-file>

use std::process::ExitCode;

use discoveryprobe_detect::detect;

fn main() -> ExitCode {
    let Some(path) = std::env::args().nth(1) else {
        eprintln!("usage: discoveryprobe-detect <source-file>");
        return ExitCode::FAILURE;
    };
    let text = match std::fs::read_to_string(&path) {
        Ok(text) => text,
        Err(err) => {
            eprintln!("read {path}: {err}");
            return ExitCode::FAILURE;
        }
    };
    match serde_json::to_string_pretty(&detect(&text)) {
        Ok(json) => {
            println!("{json}");
            ExitCode::SUCCESS
        }
        Err(err) => {
            eprintln!("serialise detections: {err}");
            ExitCode::FAILURE
        }
    }
}
