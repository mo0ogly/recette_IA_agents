//! Canonical serialization of [`Claims`] -- the exact bytes the Ed25519
//! signature covers.
//!
//! The signature is computed over a CANONICAL form of the claims so that the
//! same logical claims always sign and verify to the same bytes, regardless of
//! how the claims were constructed or in what order a JSON producer happened to
//! emit fields. This canonicalization rule is FROZEN: it is part of the wire
//! contract and MUST NOT change between versions, or previously-issued
//! passports would stop verifying.
//!
//! # Canonicalization rule (frozen)
//!
//! `canonical_bytes` emits a single JSON object with:
//!
//! - **Compact form**: no insignificant whitespace (serde_json's `Display` for
//!   [`serde_json::Value`] emits the compact representation).
//! - **Keys in ascending byte order**: `delegation`, `exp`, `id`, `scope`,
//!   `spiffe_id`, `tenant`. The keys are inserted into the map in that exact
//!   order so the output is identical whether serde_json's map is a `BTreeMap`
//!   (default, sorts keys) or an `IndexMap` (under the `preserve_order`
//!   feature, keeps insertion order) -- feature unification in a workspace can
//!   silently flip that backing store, so this crate does not rely on it.
//! - **Absent optional omitted**: when `spiffe_id` is `None`, the `spiffe_id`
//!   key is absent entirely (it is NOT emitted as `null`). This mirrors the
//!   `skip_serializing_if = "Option::is_none"` on [`Claims::spiffe_id`].
//! - **UTF-8**: the returned bytes are the UTF-8 encoding of that JSON text.
//!
//! Array element order (`delegation`, `scope`) is significant and preserved
//! verbatim -- it carries meaning (the mandate chain is ordered) and is part of
//! what the signature protects.
//!
//! The function is total and infallible by construction: it builds the JSON
//! value from owned `String`s and serializes via `Display`, which cannot fail
//! for a String-only value tree. It reads no clock and draws no randomness (I4).

use crate::Claims;
use serde_json::{Map, Value};

/// Returns the canonical, deterministic JSON bytes of `claims`.
///
/// These bytes are the message the Ed25519 signature is computed over at issue
/// time and re-derived at verify time. Two calls with logically-equal claims
/// return byte-identical output; the result is valid, compact JSON with keys in
/// ascending order. See the module documentation for the frozen canonical form.
///
/// This function never fails and has no side effects (no I/O, clock, or rand).
pub fn canonical_bytes(claims: &Claims) -> Vec<u8> {
    canonical_value(claims).to_string().into_bytes()
}

/// Builds the canonical [`serde_json::Value`] for `claims`.
///
/// Keys are inserted in ascending order so the compact serialization is stable
/// regardless of the map's backing store (see the module docs).
///
/// # Canonicalization scope limitation
///
/// This function sorts keys at the **root level only**, and is valid for the
/// current flat [`Claims`] shape where all fields are primitive (String) or
/// homogeneous arrays of primitives (Vec<String>). If a future version of
/// [`Claims`] introduces nested objects or heterogeneous collections, this
/// function would need to be extended to recursively sort all nested levels
/// to maintain canonical stability.
fn canonical_value(claims: &Claims) -> Value {
    let mut map = Map::new();
    map.insert(
        "delegation".to_string(),
        Value::Array(
            claims
                .delegation
                .iter()
                .cloned()
                .map(Value::String)
                .collect(),
        ),
    );
    map.insert("exp".to_string(), Value::String(claims.exp.clone()));
    map.insert("id".to_string(), Value::String(claims.id.clone()));
    map.insert(
        "scope".to_string(),
        Value::Array(claims.scope.iter().cloned().map(Value::String).collect()),
    );
    if let Some(spiffe_id) = &claims.spiffe_id {
        map.insert("spiffe_id".to_string(), Value::String(spiffe_id.clone()));
    }
    map.insert("tenant".to_string(), Value::String(claims.tenant.clone()));
    Value::Object(map)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A fully-populated set of claims, including the optional `spiffe_id`.
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

    #[test]
    fn canonical_bytes_are_stable_across_calls() {
        let claims = sample_claims();
        assert_eq!(canonical_bytes(&claims), canonical_bytes(&claims));
    }

    #[test]
    fn logically_equal_claims_produce_identical_bytes() {
        // Two independently-constructed but logically-equal claims.
        let a = sample_claims();
        let b = sample_claims();
        assert_eq!(canonical_bytes(&a), canonical_bytes(&b));
    }

    #[test]
    fn canonical_bytes_are_valid_parseable_json() {
        let claims = sample_claims();
        let bytes = canonical_bytes(&claims);
        let parsed: Value =
            serde_json::from_slice(&bytes).expect("canonical bytes must be valid JSON");
        let obj = parsed
            .as_object()
            .expect("canonical form must be an object");
        assert_eq!(
            obj.get("id").and_then(Value::as_str),
            Some("agent:invoice-reconciler-7")
        );
        assert_eq!(
            obj.get("delegation")
                .and_then(Value::as_array)
                .map(Vec::len),
            Some(3)
        );
    }

    #[test]
    fn keys_appear_in_ascending_order() {
        let claims = sample_claims();
        let text =
            String::from_utf8(canonical_bytes(&claims)).expect("canonical bytes are valid UTF-8");

        let pos = |needle: &str| {
            text.find(&format!("\"{needle}\":"))
                .unwrap_or_else(|| panic!("key {needle} must be present in {text}"))
        };
        // delegation < exp < id < scope < spiffe_id < tenant
        assert!(pos("delegation") < pos("exp"));
        assert!(pos("exp") < pos("id"));
        assert!(pos("id") < pos("scope"));
        assert!(pos("scope") < pos("spiffe_id"));
        assert!(pos("spiffe_id") < pos("tenant"));
    }

    #[test]
    fn absent_spiffe_id_is_omitted_not_null() {
        let mut claims = sample_claims();
        claims.spiffe_id = None;
        let text =
            String::from_utf8(canonical_bytes(&claims)).expect("canonical bytes are valid UTF-8");
        assert!(
            !text.contains("spiffe_id"),
            "absent optional must be omitted entirely, not emitted as null: {text}"
        );
    }

    #[test]
    fn canonical_form_is_compact_without_whitespace() {
        let claims = sample_claims();
        let text =
            String::from_utf8(canonical_bytes(&claims)).expect("canonical bytes are valid UTF-8");
        // Compact JSON: no newline and no ", " / ": " spacing.
        assert!(!text.contains('\n'));
        assert!(!text.contains(", "));
        assert!(!text.contains(": "));
    }
}
