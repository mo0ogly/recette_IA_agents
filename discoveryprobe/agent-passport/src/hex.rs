//! Minimal hex DECODING, private to the crate.
//!
//! The issuing path already encodes bytes to hex with a tiny local helper; the
//! trust store and the verifier need the inverse (decode a hex public key and a
//! hex signature). To keep this crate exportable with a minimal dependency set,
//! decoding is hand-rolled here rather than pulling in the `hex` crate.
//!
//! Both lowercase and uppercase hex digits are accepted so the decoder is
//! robust to either casing of an externally-supplied public key; issued
//! signatures are lowercase and decode unchanged.

/// Decodes a hexadecimal string into bytes.
///
/// Returns `None` when the input has an odd length or contains a non-hex byte.
/// This never panics and reads no external state.
///
/// Uses `% 2 != 0` rather than `is_multiple_of` for MSRV portability
/// (`is_multiple_of` requires Rust >= 1.87; this crate targets older toolchains).
#[allow(clippy::manual_is_multiple_of)]
pub(crate) fn decode_hex(text: &str) -> Option<Vec<u8>> {
    let bytes = text.as_bytes();
    if bytes.len() % 2 != 0 {
        return None;
    }
    let mut out = Vec::with_capacity(bytes.len() / 2);
    let mut i = 0;
    while i < bytes.len() {
        let hi = hex_val(bytes[i])?;
        let lo = hex_val(bytes[i + 1])?;
        out.push((hi << 4) | lo);
        i += 2;
    }
    Some(out)
}

/// Maps a single ASCII hex digit to its 0..=15 value, or `None` if not hex.
fn hex_val(byte: u8) -> Option<u8> {
    match byte {
        b'0'..=b'9' => Some(byte - b'0'),
        b'a'..=b'f' => Some(byte - b'a' + 10),
        b'A'..=b'F' => Some(byte - b'A' + 10),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn decodes_lowercase_and_uppercase() {
        assert_eq!(decode_hex("00ff"), Some(vec![0x00, 0xff]));
        assert_eq!(decode_hex("00FF"), Some(vec![0x00, 0xff]));
        assert_eq!(decode_hex("deadBEEF"), Some(vec![0xde, 0xad, 0xbe, 0xef]));
    }

    #[test]
    fn rejects_odd_length_and_non_hex() {
        assert_eq!(decode_hex("abc"), None);
        assert_eq!(decode_hex("zz"), None);
        assert_eq!(decode_hex("00gg"), None);
    }

    #[test]
    fn decodes_empty_to_empty() {
        assert_eq!(decode_hex(""), Some(vec![]));
    }
}
