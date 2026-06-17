//! The detector run over realistic multi-file repo fixtures
//! (corpus/detect/repos/<slug>/) yields each repo's ground-truth detections.
//!
//! The fixtures are the recette's OWN small projects that use the real public
//! identifiers of observability tools (package name / import / env var) -- no
//! third-party repo content. Each repo carries an `expected.json` ground-truth;
//! the scan reads the SOURCE files (excluding `expected.json`, which itself
//! contains needle strings) and asserts the detections match.

use std::path::Path;

use discoveryprobe_detect::{detect, ToolMatch};

const REPOS: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../../corpus/detect/repos");

fn scan_sources(dir: &Path) -> String {
    let mut entries: Vec<_> = std::fs::read_dir(dir)
        .expect("read repo dir")
        .map(|e| e.expect("entry").path())
        .filter(|p| p.file_name().and_then(|n| n.to_str()) != Some("expected.json"))
        .collect();
    entries.sort();
    let mut text = String::new();
    for path in entries {
        if let Ok(content) = std::fs::read_to_string(&path) {
            text.push_str(&content);
            text.push('\n');
        }
    }
    text
}

#[test]
fn every_repo_fixture_matches_its_ground_truth() {
    let mut dirs: Vec<_> = std::fs::read_dir(REPOS)
        .expect("read repos dir")
        .map(|e| e.expect("entry").path())
        .filter(|p| p.is_dir())
        .collect();
    dirs.sort();
    assert!(!dirs.is_empty(), "expected at least one repo fixture");

    for dir in dirs {
        let expected_raw =
            std::fs::read_to_string(dir.join("expected.json")).expect("read expected.json");
        let expected: Vec<ToolMatch> =
            serde_json::from_str(&expected_raw).expect("parse expected.json");
        let got = detect(&scan_sources(&dir));
        assert_eq!(
            got,
            expected,
            "detection mismatch for repo {}",
            dir.display()
        );
    }
}
