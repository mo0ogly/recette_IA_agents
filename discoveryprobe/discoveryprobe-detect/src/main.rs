//! discoveryprobe-detect CLI: report the observability tools in a source.
//!
//! Accepts a file OR a directory (scanned recursively, files concatenated) and
//! prints, as JSON, the observability tools detected (tool, category, matched
//! needle). Usage:
//!   discoveryprobe-detect <source-file-or-dir>

use std::path::Path;
use std::process::ExitCode;

use discoveryprobe_detect::detect;

/// Append every readable file under `path` (recursive, sorted) to `buf`. A
/// directory is walked in a stable order so the scan is deterministic; an
/// unreadable/binary file is skipped, not fatal.
fn collect(path: &Path, buf: &mut String) -> std::io::Result<()> {
    if path.is_dir() {
        let mut entries: Vec<_> = std::fs::read_dir(path)?.collect::<Result<_, _>>()?;
        entries.sort_by_key(std::fs::DirEntry::path);
        for entry in entries {
            collect(&entry.path(), buf)?;
        }
    } else if let Ok(text) = std::fs::read_to_string(path) {
        buf.push_str(&text);
        buf.push('\n');
    }
    Ok(())
}

fn main() -> ExitCode {
    let Some(arg) = std::env::args().nth(1) else {
        eprintln!("usage: discoveryprobe-detect <source-file-or-dir>");
        return ExitCode::FAILURE;
    };
    let mut text = String::new();
    if let Err(err) = collect(Path::new(&arg), &mut text) {
        eprintln!("scan {arg}: {err}");
        return ExitCode::FAILURE;
    }
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
