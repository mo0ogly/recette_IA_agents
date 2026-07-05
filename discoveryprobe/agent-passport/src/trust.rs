//! The trust store: the caller-supplied set of public keys the verifier trusts.
//!
//! The verifier is PURE and injects its trust anchors: a [`TrustStore`] maps a
//! `key_id` to an Ed25519 [`VerifyingKey`]. Loading a key is a SETUP step (akin
//! to reading configuration) and MAY fail with a [`PassportError::BadKey`] when
//! the supplied material is not a valid 32-byte Ed25519 public key. This is the
//! only failure surface around verification -- [`crate::verify`] itself never
//! fails (see its documentation).

use crate::hex::decode_hex;
use crate::PassportError;
use ed25519_dalek::VerifyingKey;
use std::collections::BTreeMap;

/// A deterministic map from `key_id` to the public key that verifies passports
/// sealed under that identifier.
///
/// A [`BTreeMap`] is used so iteration and any future serialization are ordered
/// and reproducible (I4). The store is injected into [`crate::verify`]; the
/// verifier never loads keys itself.
#[derive(Debug, Clone, Default)]
pub struct TrustStore {
    keys: BTreeMap<String, VerifyingKey>,
}

impl TrustStore {
    /// Creates an empty trust store.
    pub fn new() -> Self {
        Self {
            keys: BTreeMap::new(),
        }
    }

    /// Registers a public key for `key_id`, decoding it from a 32-byte hex
    /// string.
    ///
    /// # Errors
    ///
    /// Returns [`PassportError::BadKey`] when `pubkey_hex` is not valid
    /// hexadecimal, is not exactly 32 bytes, or does not decode to a valid
    /// Ed25519 point. This is a legitimate SETUP-time error and is distinct
    /// from the verify path, which never fails.
    pub fn add_hex(&mut self, key_id: &str, pubkey_hex: &str) -> Result<(), PassportError> {
        let bytes = decode_hex(pubkey_hex).ok_or_else(|| {
            PassportError::BadKey(format!("key_id {key_id}: public key is not valid hex"))
        })?;
        let array: [u8; 32] = bytes.as_slice().try_into().map_err(|_| {
            PassportError::BadKey(format!(
                "key_id {key_id}: public key must be 32 bytes, got {}",
                bytes.len()
            ))
        })?;
        let verifying_key = VerifyingKey::from_bytes(&array).map_err(|err| {
            PassportError::BadKey(format!(
                "key_id {key_id}: invalid Ed25519 public key: {err}"
            ))
        })?;
        self.keys.insert(key_id.to_string(), verifying_key);
        Ok(())
    }

    /// Returns the public key registered for `key_id`, if any.
    pub fn get(&self, key_id: &str) -> Option<&VerifyingKey> {
        self.keys.get(key_id)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ed25519_dalek::SigningKey;

    fn sample_pubkey_hex() -> String {
        let key = SigningKey::from_bytes(&[9u8; 32]);
        let bytes = key.verifying_key().to_bytes();
        let mut out = String::with_capacity(64);
        for b in bytes {
            out.push_str(&format!("{b:02x}"));
        }
        out
    }

    #[test]
    fn add_and_get_roundtrip() {
        let mut store = TrustStore::new();
        store
            .add_hex("k1", &sample_pubkey_hex())
            .expect("a valid 32-byte Ed25519 public key must load");
        assert!(store.get("k1").is_some());
        assert!(store.get("absent").is_none());
    }

    #[test]
    fn add_rejects_bad_hex() {
        let mut store = TrustStore::new();
        let err = store
            .add_hex("k1", "zz")
            .expect_err("non-hex material must be rejected");
        assert!(matches!(err, PassportError::BadKey(_)));
    }

    #[test]
    fn add_rejects_wrong_length() {
        let mut store = TrustStore::new();
        let err = store
            .add_hex("k1", "00ff")
            .expect_err("a 2-byte key is not a 32-byte Ed25519 key");
        assert!(matches!(err, PassportError::BadKey(_)));
    }
}
