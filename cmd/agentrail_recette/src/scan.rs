//! File collection and `#[cfg(test)]` region detection.

use std::path::{Path, PathBuf};

use anyhow::Result;
use walkdir::WalkDir;

/// Collect every `.rs` file under `path` (or `path` itself if it is a file),
/// skipping anything inside a `target/` build directory.
pub fn collect_rs_files(path: &Path) -> Result<Vec<PathBuf>> {
    if path.is_file() {
        return Ok(if is_rust_file(path) {
            vec![path.to_path_buf()]
        } else {
            Vec::new()
        });
    }

    let mut files = Vec::new();
    for entry in WalkDir::new(path)
        .into_iter()
        .filter_map(std::result::Result::ok)
    {
        let p = entry.path();
        if p.components().any(|c| c.as_os_str() == "target") {
            continue;
        }
        if is_rust_file(p) {
            files.push(p.to_path_buf());
        }
    }
    files.sort();
    Ok(files)
}

/// True if the path is a `.rs` file.
fn is_rust_file(p: &Path) -> bool {
    p.is_file() && p.extension().is_some_and(|e| e == "rs")
}

/// True if the path is conventionally test-only (`tests/` dir or `*_test.rs`).
pub fn is_test_path(p: &Path) -> bool {
    if p.components().any(|c| c.as_os_str() == "tests") {
        return true;
    }
    p.file_name()
        .and_then(|n| n.to_str())
        .is_some_and(|n| n.ends_with("_test.rs") || n == "tests.rs")
}

/// Find the nearest ancestor directory containing a `Cargo.toml`, used as the
/// working directory for cargo tools. Falls back to `path` (or its parent if a
/// file) when none is found.
pub fn nearest_crate_dir(path: &Path) -> PathBuf {
    let mut dir: &Path = if path.is_file() {
        path.parent().unwrap_or(path)
    } else {
        path
    };
    loop {
        if dir.join("Cargo.toml").is_file() {
            return dir.to_path_buf();
        }
        match dir.parent() {
            Some(parent) => dir = parent,
            None => break,
        }
    }
    if path.is_file() {
        path.parent()
            .unwrap_or_else(|| Path::new("."))
            .to_path_buf()
    } else {
        path.to_path_buf()
    }
}

/// Read a file's contents, returning `None` (with a stderr warning) on I/O or
/// UTF-8 errors so a single bad file never aborts the whole scan.
pub fn read_file(p: &Path) -> Option<String> {
    match std::fs::read_to_string(p) {
        Ok(s) => Some(s),
        Err(e) => {
            eprintln!("agentrail_recette: skipping {} ({e})", p.display());
            None
        }
    }
}

/// Compute, per line, whether that line sits inside a `#[cfg(test)]` block.
///
/// Heuristic: brace-depth tracking. When a `#[cfg(test)]` attribute is seen, the
/// next brace-opening line starts a test region that ends when the brace depth
/// returns to the pre-region level. Brace counting ignores string/comment
/// contents, which is acceptable for a lint-grade exclusion.
pub fn test_lines(content: &str) -> Vec<bool> {
    let mut flags = Vec::new();
    let mut depth: i32 = 0;
    let mut armed = false;
    let mut region_start: Option<i32> = None;

    for line in content.lines() {
        if line.contains("#[cfg(test)]") {
            armed = true;
        }
        let opens = line.matches('{').count() as i32;
        let closes = line.matches('}').count() as i32;

        if armed && region_start.is_none() && opens > 0 {
            region_start = Some(depth);
            armed = false;
        }

        flags.push(region_start.is_some());

        depth += opens - closes;
        if let Some(start) = region_start {
            if depth <= start {
                region_start = None;
            }
        }
    }
    flags
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_lines_flags_only_cfg_test_block() {
        let src = "\
fn real() {}
#[cfg(test)]
mod tests {
    fn helper() {}
}
fn after() {}";
        let flags = test_lines(src);
        assert!(!flags[0], "real() not in test");
        assert!(flags[3], "helper() inside test mod");
        assert!(!flags[5], "after() not in test");
    }

    #[test]
    fn is_test_path_detects_conventional_names() {
        assert!(is_test_path(Path::new("crate/tests/foo.rs")));
        assert!(is_test_path(Path::new("src/parser_test.rs")));
        assert!(!is_test_path(Path::new("src/main.rs")));
    }
}
