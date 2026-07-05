#![deny(missing_docs)]
//! Exportable, pure implementation of the "Contrat 3" signed agent passport.
//!
//! A passport is a frozen, signed tuple that binds an agent identity to a
//! mandate chain (delegation up to a human), a permitted action scope, and an
//! expiry. It is sealed with an Ed25519 signature over the canonical JSON of
//! its [`Claims`] and identified by a `key_id`.
//!
//! This crate is deliberately PURE: it performs no I/O, reads no wall clock,
//! and draws no randomness. Parsing, issuing, and verifying a passport are
//! therefore deterministic and side-effect free, which lets this crate be
//! lifted into a real-agent runtime unchanged. It has no dependency on any
//! discoveryprobe-* crate.
//!
//! This module currently provides parse-only support: the [`Claims`] and
//! [`Passport`] types and [`Passport::from_json`]. Issuing (signing) and
//! verification arrive in later tasks and reuse the same frozen shapes.

use serde::{Deserialize, Serialize};

/// The signed subset of a passport: everything the Ed25519 signature covers,
/// WITHOUT the signature itself or the `key_id`.
///
/// The set of fields is frozen: unknown fields are rejected at parse time via
/// `deny_unknown_fields` so that an attacker cannot smuggle extra attestation
/// data past the signature boundary.
#[derive(Serialize, Deserialize, Debug, Clone, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Claims {
    /// Stable identifier of the agent this passport is issued to.
    pub id: String,
    /// Tenant (governance boundary) the agent belongs to.
    pub tenant: String,
    /// Mandate chain up to a human principal, from the direct issuer outward.
    pub delegation: Vec<String>,
    /// Permitted action families (the capability scope) granted to the agent.
    pub scope: Vec<String>,
    /// Expiry as an RFC3339 timestamp, kept verbatim as a string at this layer
    /// (temporal validation is a verification concern, not a parsing one).
    pub exp: String,
    /// Optional SPIFFE identity (`spiffe://...`) bound to the agent.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub spiffe_id: Option<String>,
}

/// A complete Contrat 3 passport: the signed [`Claims`] plus the seal.
///
/// # Shape decision: flat struct, not `#[serde(flatten)]`
///
/// The signed fields are duplicated here rather than embedded via
/// `#[serde(flatten)] claims: Claims`. serde's `deny_unknown_fields` is
/// documented as incompatible with `flatten`: a flattened field consumes the
/// map opaquely, so the outer `deny_unknown_fields` cannot see or reject
/// unknown keys (and combining the two produces an error). Because rejecting
/// unknown fields is a hard requirement of a frozen attestation, the passport
/// is a flat struct carrying every signed field plus `signature` and `key_id`,
/// all under one `deny_unknown_fields`. [`Passport::claims`] reconstructs the
/// signed subset so signing/verification have a single source of truth for
/// what the signature covers.
#[derive(Serialize, Deserialize, Debug, Clone, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Passport {
    /// Stable identifier of the agent this passport is issued to.
    pub id: String,
    /// Tenant (governance boundary) the agent belongs to.
    pub tenant: String,
    /// Mandate chain up to a human principal, from the direct issuer outward.
    pub delegation: Vec<String>,
    /// Permitted action families (the capability scope) granted to the agent.
    pub scope: Vec<String>,
    /// Expiry as an RFC3339 timestamp, kept verbatim as a string at this layer.
    pub exp: String,
    /// Optional SPIFFE identity (`spiffe://...`) bound to the agent.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub spiffe_id: Option<String>,
    /// Ed25519 signature over the canonical JSON of the [`Claims`], hex-encoded.
    pub signature: String,
    /// Identifier of the public key that verifies `signature`.
    pub key_id: String,
}

impl Passport {
    /// Returns the signed subset of this passport as a [`Claims`].
    ///
    /// This is the single source of truth for what the Ed25519 signature
    /// covers; the returned value clones the signed fields and excludes
    /// `signature` and `key_id`.
    pub fn claims(&self) -> Claims {
        Claims {
            id: self.id.clone(),
            tenant: self.tenant.clone(),
            delegation: self.delegation.clone(),
            scope: self.scope.clone(),
            exp: self.exp.clone(),
            spiffe_id: self.spiffe_id.clone(),
        }
    }

    /// Parses a passport from raw JSON bytes.
    ///
    /// Unknown fields and missing required fields are rejected (frozen
    /// attestation). The error carries the underlying `serde_json` failure.
    pub fn from_json(raw: &[u8]) -> Result<Passport, PassportError> {
        let passport = serde_json::from_slice(raw)?;
        Ok(passport)
    }
}

/// Errors produced while handling a passport.
///
/// Only the variants needed for parse-only support exist today; crypto
/// variants (signing/verification) are added in later tasks.
#[derive(Debug, thiserror::Error)]
pub enum PassportError {
    /// The passport is structurally invalid in a way not captured by a JSON
    /// error (reserved for higher-level shape checks).
    #[error("malformed passport: {0}")]
    Malformed(String),
    /// The raw bytes could not be deserialized as a passport.
    #[error("json error: {0}")]
    Json(#[from] serde_json::Error),
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A realistic, fully-populated Contrat 3 passport. The signature is a
    /// real-shaped 64-byte Ed25519 value (128 hex chars); the key_id is a
    /// realistic key fingerprint.
    const VALID_PASSPORT: &str = r#"{
        "id": "agent:invoice-reconciler-7",
        "tenant": "acme-finance",
        "delegation": [
            "agent:invoice-reconciler-7",
            "service:reconciliation-orchestrator",
            "human:cfo.jdupont@acme.example"
        ],
        "scope": ["read_ledger", "post_journal_entry", "open_pr"],
        "exp": "2026-12-31T23:59:59Z",
        "spiffe_id": "spiffe://acme.example/ns/finance/sa/invoice-reconciler",
        "signature": "3d4f8a1c9b2e7f6058a1c4d2e9f0b8a7561d3c2b4e5f6a7089c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f6071829304a5b6c7",
        "key_id": "ed25519:acme-issuer-2026-q3"
    }"#;

    #[test]
    fn parses_full_valid_passport_with_every_field() {
        let passport = Passport::from_json(VALID_PASSPORT.as_bytes())
            .expect("a well-formed Contrat 3 passport must parse");

        assert_eq!(passport.id, "agent:invoice-reconciler-7");
        assert_eq!(passport.tenant, "acme-finance");
        assert_eq!(
            passport.delegation,
            vec![
                "agent:invoice-reconciler-7".to_string(),
                "service:reconciliation-orchestrator".to_string(),
                "human:cfo.jdupont@acme.example".to_string(),
            ]
        );
        assert_eq!(
            passport.scope,
            vec![
                "read_ledger".to_string(),
                "post_journal_entry".to_string(),
                "open_pr".to_string(),
            ]
        );
        assert_eq!(passport.exp, "2026-12-31T23:59:59Z");
        assert_eq!(
            passport.spiffe_id.as_deref(),
            Some("spiffe://acme.example/ns/finance/sa/invoice-reconciler")
        );
        assert_eq!(
            passport.signature,
            "3d4f8a1c9b2e7f6058a1c4d2e9f0b8a7561d3c2b4e5f6a7089c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f6071829304a5b6c7"
        );
        assert_eq!(passport.key_id, "ed25519:acme-issuer-2026-q3");
    }

    #[test]
    fn parses_valid_passport_without_optional_spiffe_id() {
        let raw = r#"{
            "id": "agent:read-only-scout",
            "tenant": "acme-finance",
            "delegation": ["agent:read-only-scout", "human:ops@acme.example"],
            "scope": ["read_ledger"],
            "exp": "2026-09-01T00:00:00Z",
            "signature": "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff",
            "key_id": "ed25519:acme-issuer-2026-q3"
        }"#;

        let passport =
            Passport::from_json(raw.as_bytes()).expect("optional spiffe_id may be absent");
        assert_eq!(passport.spiffe_id, None);
    }

    #[test]
    fn rejects_passport_missing_required_field() {
        // The `signature` field is required; without it parsing must fail.
        let raw = r#"{
            "id": "agent:invoice-reconciler-7",
            "tenant": "acme-finance",
            "delegation": ["agent:invoice-reconciler-7", "human:cfo@acme.example"],
            "scope": ["read_ledger"],
            "exp": "2026-12-31T23:59:59Z",
            "key_id": "ed25519:acme-issuer-2026-q3"
        }"#;

        let err = Passport::from_json(raw.as_bytes())
            .expect_err("a passport without a signature must be rejected");
        assert!(matches!(err, PassportError::Json(_)));
    }

    #[test]
    fn rejects_passport_with_unknown_field() {
        // `deny_unknown_fields`: an extra field outside the frozen shape must
        // be rejected so it cannot ride along past the signature boundary.
        let raw = r#"{
            "id": "agent:invoice-reconciler-7",
            "tenant": "acme-finance",
            "delegation": ["agent:invoice-reconciler-7", "human:cfo@acme.example"],
            "scope": ["read_ledger"],
            "exp": "2026-12-31T23:59:59Z",
            "signature": "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff",
            "key_id": "ed25519:acme-issuer-2026-q3",
            "elevated": true
        }"#;

        let err = Passport::from_json(raw.as_bytes())
            .expect_err("an unknown field must be rejected (deny_unknown_fields)");
        assert!(matches!(err, PassportError::Json(_)));
    }

    #[test]
    fn claims_returns_exactly_the_signed_subset() {
        let passport = Passport::from_json(VALID_PASSPORT.as_bytes())
            .expect("a well-formed Contrat 3 passport must parse");
        let claims = passport.claims();

        let expected = Claims {
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
        };
        assert_eq!(claims, expected);
    }
}
