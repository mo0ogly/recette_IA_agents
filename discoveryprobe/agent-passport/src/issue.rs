//! Issuing (signing) a passport: turn a set of [`Claims`] into a sealed
//! [`Passport`] by signing its canonical bytes with an Ed25519 key.
//!
//! The authority owns the [`SigningKey`] and chooses the `key_id`; this crate
//! never invents either. Signing is deterministic (Ed25519 signatures are a
//! pure function of key and message), so issuing the same claims with the same
//! key yields byte-identical output, which keeps the whole flow replayable (I4).
//!
//! # Hex encoding decision
//!
//! The 64 signature bytes are rendered as 128 lowercase hex characters by a
//! tiny private [`to_hex`] helper rather than pulling in the `hex` crate. The
//! encoding is trivial (two `{:02x}` digits per byte) and avoiding a dependency
//! keeps this exportable crate minimal.

use crate::{canonical_bytes, Claims, Passport, PassportError};
use ed25519_dalek::{Signer, SigningKey};
use std::fmt::Write as _;

/// Issues a sealed [`Passport`] for `claims`, signed with `signing_key`.
///
/// The signature covers [`canonical_bytes`] of `claims`; the resulting
/// passport carries the same signed fields plus the lowercase-hex signature
/// (128 characters) and the caller-provided `key_id`.
///
/// # Errors
///
/// This function currently has **no failure path**: Ed25519 signing over the
/// infallible canonical bytes cannot fail, so it always returns `Ok`. The
/// `Result` is kept for API symmetry and forward compatibility -- a future
/// canonicalization that can fail (or an issuer-side validation step) stays
/// source-compatible, and callers (e.g. a CLI) map [`PassportError`]
/// uniformly.
pub fn issue(
    claims: Claims,
    signing_key: &SigningKey,
    key_id: &str,
) -> Result<Passport, PassportError> {
    let message = canonical_bytes(&claims);
    let signature = signing_key.sign(&message);
    let signature_hex = to_hex(&signature.to_bytes());

    Ok(Passport {
        id: claims.id,
        tenant: claims.tenant,
        delegation: claims.delegation,
        scope: claims.scope,
        exp: claims.exp,
        spiffe_id: claims.spiffe_id,
        signature: signature_hex,
        key_id: key_id.to_string(),
    })
}

/// Encodes `bytes` as a lowercase hexadecimal string (two digits per byte).
///
/// Writing to a `String` via `write!` cannot fail, so the formatting result is
/// intentionally discarded; the function is total.
fn to_hex(bytes: &[u8]) -> String {
    let mut out = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        // Writing to a String never returns an error.
        let _ = write!(out, "{byte:02x}");
    }
    out
}
