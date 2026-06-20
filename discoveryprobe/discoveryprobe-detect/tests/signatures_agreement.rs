//! The committed signature table (corpus/detect/observability-signatures.json)
//! is the single source of truth shared with the Python API. This test asserts
//! the Rust static `SIGNATURES` matches it byte-for-byte (tool, category,
//! needles, order) -- so the two engines can never silently diverge (R20).

use discoveryprobe_detect::{signatures, Category};
use serde::Deserialize;

const SHARED: &str = concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../corpus/detect/observability-signatures.json"
);

#[derive(Deserialize)]
struct LoadedSignature {
    tool: String,
    category: Category,
    capabilities: Vec<Category>,
    needles: Vec<String>,
}

#[test]
fn rust_table_matches_the_shared_signature_json() {
    let raw = std::fs::read_to_string(SHARED).expect("read shared signatures");
    let loaded: Vec<LoadedSignature> = serde_json::from_str(&raw).expect("parse shared signatures");

    let rust = signatures();
    assert_eq!(
        loaded.len(),
        rust.len(),
        "tool count differs from the shared table"
    );
    for (l, r) in loaded.iter().zip(rust.iter()) {
        assert_eq!(l.tool, r.tool, "tool name mismatch");
        assert_eq!(l.category, r.category, "category mismatch for {}", r.tool);
        assert_eq!(
            l.capabilities,
            r.capabilities.to_vec(),
            "capabilities mismatch for {}",
            r.tool
        );
        let r_needles: Vec<String> = r.needles.iter().map(|s| s.to_string()).collect();
        assert_eq!(l.needles, r_needles, "needles mismatch for {}", r.tool);
    }
}
