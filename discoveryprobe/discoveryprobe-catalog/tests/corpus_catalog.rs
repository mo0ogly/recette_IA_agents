//! The committed corpus catalog (corpus/catalog/agent-registry.json) parses and
//! projects to the expected discovery invariants -- ground-truth wiring, so a
//! malformed or duplicated corpus catalog turns this test red (R20: a coverage
//! gap is a failing test, never found by hand).

use discoveryprobe_catalog::CatalogRegistry;

const CORPUS_CATALOG: &str = concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../corpus/catalog/agent-registry.json"
);

fn load() -> CatalogRegistry {
    let raw = std::fs::read_to_string(CORPUS_CATALOG).expect("read corpus catalog");
    CatalogRegistry::from_json(&raw).expect("parse corpus catalog")
}

#[test]
fn corpus_catalog_parses_without_duplicates() {
    let reg = load();
    assert!(!reg.is_empty(), "corpus catalog must declare agents");
    assert!(
        !reg.has_duplicate_names(),
        "corpus catalog agent names must be unique"
    );
}

#[test]
fn corpus_catalog_summary_is_invariant_and_deterministic() {
    let reg = load();
    let summary = reg.summary();
    assert_eq!(summary.total, summary.unique, "no duplicate names");
    assert!(
        summary.with_tools >= 1,
        "at least one agent declares a tool"
    );
    assert!(
        !summary.tags.is_empty(),
        "the catalog should expose some tags"
    );
    // Tags are sorted + de-duplicated.
    let mut sorted = summary.tags.clone();
    sorted.sort();
    sorted.dedup();
    assert_eq!(summary.tags, sorted);
    // Deterministic: a second parse yields the same projection.
    assert_eq!(summary, load().summary());
}
