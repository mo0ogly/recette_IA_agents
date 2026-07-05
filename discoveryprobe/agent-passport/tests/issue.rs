//! Integration tests for issuing a passport with real Ed25519 keys.
//!
//! Determinism (I4): the signing key is derived from a FIXED 32-byte seed, so
//! these tests draw no randomness and are byte-stable across runs.

use agent_passport::{canonical_bytes, issue, Claims};
use ed25519_dalek::{Signature, SigningKey, Verifier};

/// A fixed, non-random test seed so the key -- and therefore the signature --
/// is deterministic.
const TEST_SEED: [u8; 32] = [7u8; 32];

/// Builds a deterministic signing key from the fixed test seed.
fn test_key() -> SigningKey {
    SigningKey::from_bytes(&TEST_SEED)
}

/// A fully-populated set of claims to issue against.
fn sample_claims() -> Claims {
    Claims {
        id: "agent:invoice-reconciler-7".to_string(),
        tenant: "acme-finance".to_string(),
        delegation: vec![
            "agent:invoice-reconciler-7".to_string(),
            "service:reconciliation-orchestrator".to_string(),
            "human:cfo.jdupont@acme.example".to_string(),
        ],
        scope: vec![
            "read_ledger".to_string(),
            "post_journal_entry".to_string(),
            "open_pr".to_string(),
        ],
        exp: "2026-12-31T23:59:59Z".to_string(),
        spiffe_id: Some("spiffe://acme.example/ns/finance/sa/invoice-reconciler".to_string()),
    }
}

/// Decodes a lowercase-hex string into bytes for verification.
fn from_hex(text: &str) -> Vec<u8> {
    assert!(
        text.len().is_multiple_of(2),
        "hex string must have even length"
    );
    (0..text.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&text[i..i + 2], 16).expect("valid hex byte"))
        .collect()
}

#[test]
fn issue_produces_passport_carrying_the_signed_claims() {
    let claims = sample_claims();
    let passport = issue(claims.clone(), &test_key(), "test-key-1")
        .expect("issuing valid claims must succeed");

    // The signed subset round-trips back to the input claims.
    assert_eq!(passport.claims(), claims);
    assert_eq!(passport.key_id, "test-key-1");
}

#[test]
fn issued_signature_verifies_with_the_public_key() {
    let claims = sample_claims();
    let key = test_key();
    let passport =
        issue(claims.clone(), &key, "test-key-1").expect("issuing valid claims must succeed");

    let signature_bytes = from_hex(&passport.signature);
    let signature =
        Signature::from_slice(&signature_bytes).expect("issued signature must be 64 bytes");

    key.verifying_key()
        .verify(canonical_bytes(&claims).as_slice(), &signature)
        .expect("the issued signature must verify over the canonical claims");
}

#[test]
fn signature_is_exactly_128_lowercase_hex_chars() {
    let passport = issue(sample_claims(), &test_key(), "test-key-1")
        .expect("issuing valid claims must succeed");

    assert_eq!(passport.signature.len(), 128);
    assert!(
        passport
            .signature
            .chars()
            .all(|c| c.is_ascii_digit() || ('a'..='f').contains(&c)),
        "signature must be lowercase hex: {}",
        passport.signature
    );
}

#[test]
fn issuing_is_deterministic_byte_stable_signature() {
    // Ed25519 signatures are deterministic: same key + same message -> same
    // signature bytes (I4).
    let a = issue(sample_claims(), &test_key(), "test-key-1")
        .expect("issuing valid claims must succeed");
    let b = issue(sample_claims(), &test_key(), "test-key-1")
        .expect("issuing valid claims must succeed");
    assert_eq!(a.signature, b.signature);
}
