//! Integration tests for the fail-safe verification path.
//!
//! Determinism (I4): keys derive from a FIXED 32-byte seed and the clock is an
//! injected [`Timestamp`] input, so these tests draw no randomness, read no wall
//! clock, and are byte-stable across runs.
//!
//! The central contract under test: [`verify`] NEVER returns an error and never
//! panics. A rotten passport yields [`Verdict::Untrusted`] carrying every
//! applicable [`UntrustReason`]; only trust-store SETUP ([`TrustStore::add_hex`])
//! and timestamp parsing can fail, which is not the verify path.

use agent_passport::{
    issue, verify, Claims, DeclaredScope, Passport, Timestamp, TrustStore, UntrustReason, Verdict,
};
use ed25519_dalek::SigningKey;

/// A fixed, non-random test seed so the key -- and therefore the signature --
/// is deterministic.
const TEST_SEED: [u8; 32] = [7u8; 32];

/// Builds a deterministic signing key from the fixed test seed.
fn test_key() -> SigningKey {
    SigningKey::from_bytes(&TEST_SEED)
}

/// Encodes bytes as lowercase hex (needed to load the public key into the store).
fn hex_encode(bytes: &[u8]) -> String {
    let mut out = String::with_capacity(bytes.len() * 2);
    for b in bytes {
        out.push_str(&format!("{b:02x}"));
    }
    out
}

/// A trust store containing exactly the public key for `key_id`.
fn trust_with_test_key(key_id: &str) -> TrustStore {
    let mut store = TrustStore::new();
    let pubkey_hex = hex_encode(test_key().verifying_key().as_bytes());
    store
        .add_hex(key_id, &pubkey_hex)
        .expect("a real 32-byte Ed25519 public key must load");
    store
}

/// Builds claims with caller-chosen delegation, scope and expiry; the identity
/// fields are fixed and irrelevant to verification.
fn claims_with(delegation: Vec<&str>, scope: Vec<&str>, exp: &str) -> Claims {
    claims_with_spiffe(delegation, scope, exp, None)
}

/// Builds claims with caller-chosen delegation, scope, expiry, and optional spiffe_id.
fn claims_with_spiffe(
    delegation: Vec<&str>,
    scope: Vec<&str>,
    exp: &str,
    spiffe_id: Option<&str>,
) -> Claims {
    Claims {
        id: "agent:subject".to_string(),
        tenant: "acme-finance".to_string(),
        delegation: delegation.into_iter().map(String::from).collect(),
        scope: scope.into_iter().map(String::from).collect(),
        exp: exp.to_string(),
        spiffe_id: spiffe_id.map(String::from),
    }
}

/// Issues a sealed passport for the given claims under `key_id`.
fn issue_passport(claims: Claims, key_id: &str) -> Passport {
    issue(claims, &test_key(), key_id).expect("issuing valid claims must succeed")
}

/// A clock instant well before every future expiry used below.
fn now() -> Timestamp {
    Timestamp::parse("2026-07-01T00:00:00Z").expect("fixed now must parse")
}

#[test]
fn fresh_passport_is_trusted() {
    let key_id = "test-key-1";
    let claims = claims_with(
        vec!["service:orch", "human:alice@acme.example"],
        vec!["read_ledger", "post_journal_entry"],
        "2027-01-01T00:00:00Z",
    );
    let passport = issue_passport(claims, key_id);
    let trust = trust_with_test_key(key_id);
    let declared = DeclaredScope::new(vec!["read_ledger".to_string()]);

    let verdict = verify(&passport, &trust, &now(), Some(&declared));
    assert_eq!(verdict, Verdict::Trusted);
}

#[test]
fn unknown_key_id_is_untrusted_without_bad_signature() {
    let claims = claims_with(
        vec!["service:orch", "human:alice@acme.example"],
        vec!["read_ledger"],
        "2027-01-01T00:00:00Z",
    );
    let passport = issue_passport(claims, "test-key-1");
    // Empty trust store: the key_id resolves to nothing.
    let trust = TrustStore::new();

    let verdict = verify(&passport, &trust, &now(), None);
    match verdict {
        Verdict::Untrusted { reasons } => {
            assert!(reasons.contains(&UntrustReason::UnknownKeyId));
            assert!(
                !reasons.contains(&UntrustReason::BadSignature),
                "signature check must be SKIPPED when the key is unknown"
            );
        }
        Verdict::Trusted => panic!("an unknown key_id must not be trusted"),
    }
}

#[test]
fn tampered_claim_yields_bad_signature() {
    let key_id = "test-key-1";
    let claims = claims_with(
        vec!["service:orch", "human:alice@acme.example"],
        vec!["read_ledger"],
        "2027-01-01T00:00:00Z",
    );
    let mut passport = issue_passport(claims, key_id);
    // Tamper a signed field AFTER sealing: the old signature no longer covers
    // the mutated canonical claims.
    passport.scope.push("delete_ledger".to_string());
    let trust = trust_with_test_key(key_id);

    let verdict = verify(&passport, &trust, &now(), None);
    match verdict {
        Verdict::Untrusted { reasons } => {
            assert!(reasons.contains(&UntrustReason::BadSignature));
        }
        Verdict::Trusted => panic!("a tampered passport must not be trusted"),
    }
}

#[test]
fn expired_passport_yields_expired() {
    let key_id = "test-key-1";
    let claims = claims_with(
        vec!["service:orch", "human:alice@acme.example"],
        vec!["read_ledger"],
        "2020-01-01T00:00:00Z",
    );
    let passport = issue_passport(claims, key_id);
    let trust = trust_with_test_key(key_id);

    let verdict = verify(&passport, &trust, &now(), None);
    match verdict {
        Verdict::Untrusted { reasons } => {
            assert!(reasons.contains(&UntrustReason::Expired));
        }
        Verdict::Trusted => panic!("an expired passport must not be trusted"),
    }
}

#[test]
fn empty_delegation_yields_empty_delegation_only() {
    let key_id = "test-key-1";
    let claims = claims_with(vec![], vec!["read_ledger"], "2027-01-01T00:00:00Z");
    let passport = issue_passport(claims, key_id);
    let trust = trust_with_test_key(key_id);

    let verdict = verify(&passport, &trust, &now(), None);
    match verdict {
        Verdict::Untrusted { reasons } => {
            assert!(reasons.contains(&UntrustReason::EmptyDelegation));
            assert!(
                !reasons.contains(&UntrustReason::NoHumanPrincipal),
                "empty delegation reports EmptyDelegation only, not also NoHumanPrincipal"
            );
        }
        Verdict::Trusted => panic!("an empty delegation must not be trusted"),
    }
}

#[test]
fn non_human_terminal_yields_no_human_principal() {
    let key_id = "test-key-1";
    let claims = claims_with(
        vec!["service:orch", "svc:bot"],
        vec!["read_ledger"],
        "2027-01-01T00:00:00Z",
    );
    let passport = issue_passport(claims, key_id);
    let trust = trust_with_test_key(key_id);

    let verdict = verify(&passport, &trust, &now(), None);
    match verdict {
        Verdict::Untrusted { reasons } => {
            assert!(reasons.contains(&UntrustReason::NoHumanPrincipal));
        }
        Verdict::Trusted => panic!("a chain not terminating on a human must not be trusted"),
    }
}

#[test]
fn scope_overreach_reports_sorted_extra_families() {
    let key_id = "test-key-1";
    let claims = claims_with(
        vec!["service:orch", "human:alice@acme.example"],
        vec!["read", "write"],
        "2027-01-01T00:00:00Z",
    );
    let passport = issue_passport(claims, key_id);
    let trust = trust_with_test_key(key_id);
    let declared = DeclaredScope::new(vec![
        "read".to_string(),
        "write".to_string(),
        "delete".to_string(),
    ]);

    let verdict = verify(&passport, &trust, &now(), Some(&declared));
    match verdict {
        Verdict::Untrusted { reasons } => {
            assert!(reasons.contains(&UntrustReason::ScopeOverreach {
                extra: vec!["delete".to_string()],
            }));
        }
        Verdict::Trusted => panic!("declared scope exceeding passport scope must not be trusted"),
    }
}

#[test]
fn malformed_exp_yields_malformed_field() {
    let key_id = "test-key-1";
    let claims = claims_with(
        vec!["service:orch", "human:alice@acme.example"],
        vec!["read_ledger"],
        "not-a-date",
    );
    let passport = issue_passport(claims, key_id);
    let trust = trust_with_test_key(key_id);

    let verdict = verify(&passport, &trust, &now(), None);
    match verdict {
        Verdict::Untrusted { reasons } => {
            assert!(reasons.contains(&UntrustReason::MalformedField("exp".to_string())));
        }
        Verdict::Trusted => panic!("a malformed exp must not be trusted"),
    }
}

#[test]
fn multiple_reasons_accumulate() {
    let key_id = "test-key-1";
    // Expired AND empty delegation at once.
    let claims = claims_with(vec![], vec!["read_ledger"], "2020-01-01T00:00:00Z");
    let passport = issue_passport(claims, key_id);
    let trust = trust_with_test_key(key_id);

    let verdict = verify(&passport, &trust, &now(), None);
    match verdict {
        Verdict::Untrusted { reasons } => {
            assert!(reasons.contains(&UntrustReason::Expired));
            assert!(reasons.contains(&UntrustReason::EmptyDelegation));
        }
        Verdict::Trusted => panic!("multiple defects must not be trusted"),
    }
}

#[test]
fn verify_is_deterministic() {
    let key_id = "test-key-1";
    let claims = claims_with(
        vec!["service:orch", "human:alice@acme.example"],
        vec!["read_ledger"],
        "2027-01-01T00:00:00Z",
    );
    let passport = issue_passport(claims, key_id);
    let trust = trust_with_test_key(key_id);

    let a = verify(&passport, &trust, &now(), None);
    let b = verify(&passport, &trust, &now(), None);
    assert_eq!(a, b);
}

#[test]
fn spiffe_id_round_trip_through_verify_is_trusted() {
    // Proves the spiffe_id field round-trips through issue and verify
    // end-to-end: canonical_bytes includes the Some-branch, Passport::claims()
    // clones it, and verify's signature check covers it.
    let key_id = "test-key-1";
    let claims = claims_with_spiffe(
        vec!["service:orch", "human:alice@acme.example"],
        vec!["read_ledger"],
        "2027-01-01T00:00:00Z",
        Some("spiffe://cluster/ns/agent"),
    );
    let passport = issue_passport(claims, key_id);
    let trust = trust_with_test_key(key_id);
    let declared = DeclaredScope::new(vec!["read_ledger".to_string()]);

    // Verify that spiffe_id is preserved in the passport.
    assert_eq!(
        passport.spiffe_id.as_deref(),
        Some("spiffe://cluster/ns/agent")
    );

    // Verify with a future clock, valid delegation, and subset scope -> Trusted.
    let verdict = verify(&passport, &trust, &now(), Some(&declared));
    assert_eq!(verdict, Verdict::Trusted);
}

#[test]
fn timestamp_epoch_conversion_matches_known_dates() {
    // Unix epoch origin.
    assert_eq!(
        Timestamp::parse("1970-01-01T00:00:00Z")
            .expect("epoch origin must parse")
            .epoch_seconds(),
        0
    );
    // Y2K, a well-known constant.
    assert_eq!(
        Timestamp::parse("2000-01-01T00:00:00Z")
            .expect("Y2K must parse")
            .epoch_seconds(),
        946_684_800
    );
    // Leap day 2024-02-29 (proves February 29 is accepted in a leap year).
    assert_eq!(
        Timestamp::parse("2024-02-29T00:00:00Z")
            .expect("leap day must parse")
            .epoch_seconds(),
        1_709_164_800
    );
    // End of year, one second before Y2K.
    assert_eq!(
        Timestamp::parse("1999-12-31T23:59:59Z")
            .expect("end of 1999 must parse")
            .epoch_seconds(),
        946_684_799
    );
    // Fractional seconds are parsed and truncated toward the second.
    assert_eq!(
        Timestamp::parse("2000-01-01T00:00:00.500Z")
            .expect("fractional seconds must parse")
            .epoch_seconds(),
        946_684_800
    );
}

#[test]
fn timestamp_rejects_non_utc_and_garbage() {
    assert!(Timestamp::parse("2027-01-01T00:00:00+01:00").is_err());
    assert!(Timestamp::parse("2027-01-01T00:00:00").is_err());
    assert!(Timestamp::parse("2023-02-29T00:00:00Z").is_err());
    assert!(Timestamp::parse("2027-13-01T00:00:00Z").is_err());
    assert!(Timestamp::parse("not-a-date").is_err());
}
