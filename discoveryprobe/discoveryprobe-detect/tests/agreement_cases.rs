//! Cross-language behaviour agreement: the Rust detector produces exactly the
//! detections in the shared cases file (corpus/detect/agreement-cases.json),
//! which the Python API tests against too -- so the two `detect` algorithms can
//! never silently diverge (table parity is covered separately by the shared
//! signature JSON; this covers ALGORITHM parity).

use discoveryprobe_detect::{detect, ToolMatch};
use serde::Deserialize;

const CASES: &str = concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../corpus/detect/agreement-cases.json"
);

#[derive(Deserialize)]
struct Case {
    text: String,
    expected: Vec<ToolMatch>,
}

#[test]
fn rust_detector_matches_the_shared_agreement_cases() {
    let raw = std::fs::read_to_string(CASES).expect("read agreement cases");
    let cases: Vec<Case> = serde_json::from_str(&raw).expect("parse agreement cases");
    assert!(!cases.is_empty(), "agreement cases must not be empty");
    for case in cases {
        assert_eq!(
            detect(&case.text),
            case.expected,
            "rust detection diverged on case text: {:?}",
            case.text
        );
    }
}
