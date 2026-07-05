//! Fail-safe verification: the core boundary of this crate.
//!
//! [`verify`] takes a parsed [`Passport`], an injected [`TrustStore`], an
//! injected clock [`Timestamp`], and an optional [`DeclaredScope`], and returns
//! a [`Verdict`] UNCONDITIONALLY. It has no `Result`, performs no I/O, reads no
//! wall clock, draws no randomness, and never panics. A rotten passport is
//! [`Verdict::Untrusted`] carrying EVERY applicable [`UntrustReason`], never an
//! error. Only PARSING ([`Passport::from_json`]) and SETUP
//! ([`TrustStore::add_hex`], [`Timestamp::parse`]) can fail.
//!
//! This is the fail-safe design: verification cannot throw, so a caller in the
//! governance decision path can never accidentally treat a verification failure
//! as an allow. The absence of any accumulated reason -- and only that -- yields
//! [`Verdict::Trusted`].
//!
//! [`Passport::from_json`]: crate::Passport::from_json
//! [`TrustStore::add_hex`]: crate::TrustStore::add_hex

use crate::hex::decode_hex;
use crate::{canonical_bytes, Passport, PassportError, TrustStore};
use ed25519_dalek::{Signature, Verifier};

/// An RFC3339 UTC instant, reduced to whole epoch seconds for comparison.
///
/// # Accepted grammar (frozen, hand-rolled parser)
///
/// ```text
/// YYYY-MM-DDTHH:MM:SS[.fraction]Z
/// ```
///
/// - `YYYY` (4 digits), `MM`, `DD`, `HH`, `MM`, `SS` (2 digits each).
/// - The literal date/time separator `T` and the mandatory UTC designator `Z`.
/// - An OPTIONAL fractional-seconds part `.fraction` (one or more digits). It is
///   parsed for validity but TRUNCATED toward the second: sub-second precision
///   does not affect [`epoch_seconds`](Timestamp::epoch_seconds) or comparison.
/// - Calendar fields are range- and leap-year-validated (e.g. `2023-02-29` is
///   rejected, `2024-02-29` accepted). Seconds are `00..=59` (a leap second `60`
///   is rejected).
///
/// Non-UTC offsets (`+01:00`, `-05:00`) and a missing `Z` are rejected: the
/// Contrat 3 `exp` is specified as RFC3339 UTC with a `Z`. Rejecting anything
/// else keeps expiry comparison unambiguous with zero timezone logic.
///
/// # Timestamp decision: hand-rolled vs a date crate
///
/// The parser is hand-rolled (Howard Hinnant's `days_from_civil` civil-calendar
/// algorithm) rather than depending on `chrono` or `time`, to keep this crate
/// zero-extra-dependency and trivially exportable. The epoch conversion is
/// tested against known constants (Unix epoch, Y2K, a leap day, an end-of-year
/// boundary, and a fractional-seconds value) in the integration tests.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub struct Timestamp {
    epoch_seconds: i64,
}

impl Timestamp {
    /// Parses an RFC3339 UTC timestamp per the grammar documented on
    /// [`Timestamp`].
    ///
    /// # Errors
    ///
    /// Returns [`PassportError::Malformed`] when `text` does not match the
    /// accepted grammar (wrong shape, out-of-range calendar field, non-UTC
    /// offset, or missing `Z`). This is a SETUP concern; a malformed `exp` seen
    /// during [`verify`] is turned into an [`UntrustReason::MalformedField`]
    /// rather than propagated.
    pub fn parse(text: &str) -> Result<Timestamp, PassportError> {
        let malformed =
            || PassportError::Malformed(format!("invalid RFC3339 UTC timestamp: {text:?}"));

        let body = text.strip_suffix('Z').ok_or_else(malformed)?;
        let (date, time) = body.split_once('T').ok_or_else(malformed)?;

        let date_parts: Vec<&str> = date.split('-').collect();
        if date_parts.len() != 3
            || date_parts[0].len() != 4
            || date_parts[1].len() != 2
            || date_parts[2].len() != 2
        {
            return Err(malformed());
        }
        let year = parse_fixed(date_parts[0]).ok_or_else(malformed)?;
        let month = parse_fixed(date_parts[1]).ok_or_else(malformed)?;
        let day = parse_fixed(date_parts[2]).ok_or_else(malformed)?;

        // Split off an optional fractional-seconds part; it must be all digits.
        let time_main = match time.split_once('.') {
            Some((main, fraction)) => {
                if fraction.is_empty() || !fraction.bytes().all(|b| b.is_ascii_digit()) {
                    return Err(malformed());
                }
                main
            }
            None => time,
        };
        let time_parts: Vec<&str> = time_main.split(':').collect();
        if time_parts.len() != 3
            || time_parts[0].len() != 2
            || time_parts[1].len() != 2
            || time_parts[2].len() != 2
        {
            return Err(malformed());
        }
        let hour = parse_fixed(time_parts[0]).ok_or_else(malformed)?;
        let minute = parse_fixed(time_parts[1]).ok_or_else(malformed)?;
        let second = parse_fixed(time_parts[2]).ok_or_else(malformed)?;

        if !(1..=12).contains(&month) {
            return Err(malformed());
        }
        if !(1..=days_in_month(year, month)).contains(&day) {
            return Err(malformed());
        }
        if hour > 23 || minute > 59 || second > 59 {
            return Err(malformed());
        }

        let days = days_from_civil(year, month, day);
        let epoch_seconds = days * 86_400 + hour * 3_600 + minute * 60 + second;
        Ok(Timestamp { epoch_seconds })
    }

    /// Returns the instant as whole seconds since the Unix epoch (UTC).
    pub fn epoch_seconds(&self) -> i64 {
        self.epoch_seconds
    }
}

/// Parses a fixed-width, all-ASCII-digit field into an `i64`, or `None`.
fn parse_fixed(text: &str) -> Option<i64> {
    if text.is_empty() || !text.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    text.parse::<i64>().ok()
}

/// Returns `true` for a Gregorian leap year.
///
/// Uses `% == 0` rather than `is_multiple_of` for MSRV portability
/// (`is_multiple_of` requires Rust >= 1.87; this crate targets older toolchains).
#[allow(clippy::manual_is_multiple_of)]
fn is_leap(year: i64) -> bool {
    (year % 4 == 0 && year % 100 != 0) || year % 400 == 0
}

/// Returns the number of days in `month` of `year` (month is `1..=12`).
fn days_in_month(year: i64, month: i64) -> i64 {
    match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 => {
            if is_leap(year) {
                29
            } else {
                28
            }
        }
        _ => 0,
    }
}

/// Days from the Unix epoch (1970-01-01) to `year-month-day`, via Howard
/// Hinnant's civil-calendar algorithm (public domain). Negative for dates
/// before the epoch.
fn days_from_civil(year: i64, month: i64, day: i64) -> i64 {
    let y = if month <= 2 { year - 1 } else { year };
    let era = if y >= 0 { y } else { y - 399 } / 400;
    let year_of_era = y - era * 400; // [0, 399]
    let month_index = (month + 9) % 12; // Mar=0 .. Feb=11
    let day_of_year = (153 * month_index + 2) / 5 + day - 1; // [0, 365]
    let day_of_era = year_of_era * 365 + year_of_era / 4 - year_of_era / 100 + day_of_year;
    era * 146_097 + day_of_era - 719_468
}

/// One concrete reason a passport is not trusted.
///
/// Derives [`Ord`] so a caller (a later task) can sort a reason list into a
/// deterministic order before rendering or hashing.
#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
pub enum UntrustReason {
    /// The Ed25519 signature did not verify (or was not decodable) against the
    /// trusted key.
    BadSignature,
    /// The passport expiry (`exp`) is at or before the injected clock.
    Expired,
    /// The mandate chain (`delegation`) is empty: there is no principal at all.
    EmptyDelegation,
    /// The mandate chain does not terminate on a human principal.
    NoHumanPrincipal,
    /// The declared scope requests families the passport does not grant.
    ScopeOverreach {
        /// The declared families absent from the passport scope, sorted.
        extra: Vec<String>,
    },
    /// The `key_id` is not present in the trust store; the signature could not
    /// be checked.
    UnknownKeyId,
    /// A field could not be interpreted; the payload names the offending field.
    MalformedField(String),
}

/// The outcome of [`verify`]: either fully trusted, or untrusted with the full
/// set of accumulated reasons.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Verdict {
    /// No defect was found: the passport is authentic, unexpired, terminates on
    /// a human, and (if a declared scope was supplied) stays within scope.
    Trusted,
    /// At least one defect was found; `reasons` lists every applicable one.
    Untrusted {
        /// Every [`UntrustReason`] that applied, in reason-check order.
        reasons: Vec<UntrustReason>,
    },
}

/// The action families a consumer's MANIFEST declares for the agent.
///
/// The library does not read a manifest: the consumer supplies the declared
/// families so [`verify`] can check the passport does not grant less than what
/// is declared (a declared family absent from the passport scope is an
/// overreach in the declaration relative to the seal).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DeclaredScope {
    /// The declared action families supplied by the consumer.
    pub families: Vec<String>,
}

impl DeclaredScope {
    /// Wraps a list of declared action families.
    pub fn new(families: Vec<String>) -> Self {
        Self { families }
    }
}

/// Verifies `passport` against injected trust anchors and clock, returning a
/// [`Verdict`] unconditionally.
///
/// This function NEVER returns an error and NEVER panics -- it is the fail-safe
/// boundary of the crate. Every applicable defect is accumulated; the checks
/// are, in order:
///
/// 1. **Signature.** If `key_id` is absent from `trust`, push
///    [`UntrustReason::UnknownKeyId`] and SKIP the signature check (it cannot be
///    performed without the key). Otherwise, decode the hex signature and verify
///    it over the [`canonical_bytes`] of the passport's claims; any failure
///    pushes [`UntrustReason::BadSignature`].
/// 2. **Expiry.** Parse `exp`; a parse failure pushes
///    [`UntrustReason::MalformedField`] for `"exp"`. Otherwise, if `exp <= now`
///    (expired at exactly `exp`), push [`UntrustReason::Expired`].
/// 3. **Delegation.** An empty chain pushes [`UntrustReason::EmptyDelegation`]
///    (and NOT also [`UntrustReason::NoHumanPrincipal`]). A non-empty chain
///    whose terminal entry is not a human principal pushes
///    [`UntrustReason::NoHumanPrincipal`]. The human rule (documented): the
///    terminal entry starts with `"human:"` OR contains `'@'` (email-like).
/// 4. **Scope** (only when `declared` is `Some`). Every declared family must be
///    within `passport.scope`; the sorted set of declared families NOT present
///    pushes [`UntrustReason::ScopeOverreach`].
///
/// With no accumulated reason the result is [`Verdict::Trusted`]; otherwise
/// [`Verdict::Untrusted`] carrying the reasons in check order.
pub fn verify(
    passport: &Passport,
    trust: &TrustStore,
    now: &Timestamp,
    declared: Option<&DeclaredScope>,
) -> Verdict {
    let mut reasons: Vec<UntrustReason> = Vec::new();

    // 1. Signature.
    match trust.get(&passport.key_id) {
        None => reasons.push(UntrustReason::UnknownKeyId),
        Some(verifying_key) => {
            let signature_ok = decode_hex(&passport.signature)
                .and_then(|bytes| Signature::from_slice(&bytes).ok())
                .map(|signature| {
                    let message = canonical_bytes(&passport.claims());
                    verifying_key.verify(message.as_slice(), &signature).is_ok()
                })
                .unwrap_or(false);
            if !signature_ok {
                reasons.push(UntrustReason::BadSignature);
            }
        }
    }

    // 2. Expiry.
    match Timestamp::parse(&passport.exp) {
        Err(_) => reasons.push(UntrustReason::MalformedField("exp".to_string())),
        Ok(exp) => {
            if exp.epoch_seconds() <= now.epoch_seconds() {
                reasons.push(UntrustReason::Expired);
            }
        }
    }

    // 3. Delegation.
    match passport.delegation.last() {
        None => reasons.push(UntrustReason::EmptyDelegation),
        Some(terminal) => {
            if !is_human_principal(terminal) {
                reasons.push(UntrustReason::NoHumanPrincipal);
            }
        }
    }

    // 4. Scope (only when the consumer supplied a declared scope).
    if let Some(declared) = declared {
        let mut extra: Vec<String> = declared
            .families
            .iter()
            .filter(|family| !passport.scope.contains(*family))
            .cloned()
            .collect();
        extra.sort();
        if !extra.is_empty() {
            reasons.push(UntrustReason::ScopeOverreach { extra });
        }
    }

    if reasons.is_empty() {
        Verdict::Trusted
    } else {
        Verdict::Untrusted { reasons }
    }
}

/// Returns `true` when a delegation entry denotes a human principal.
///
/// Rule (frozen): the entry starts with the `"human:"` prefix OR contains an
/// `'@'` (email-like). This mirrors the corpus delegation convention
/// (`human:cfo.jdupont@acme.example`).
fn is_human_principal(entry: &str) -> bool {
    entry.starts_with("human:") || entry.contains('@')
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn epoch_of_known_dates() {
        assert_eq!(
            Timestamp::parse("1970-01-01T00:00:00Z")
                .expect("epoch origin")
                .epoch_seconds(),
            0
        );
        assert_eq!(
            Timestamp::parse("2000-01-01T00:00:00Z")
                .expect("Y2K")
                .epoch_seconds(),
            946_684_800
        );
        assert_eq!(
            Timestamp::parse("2024-02-29T00:00:00Z")
                .expect("leap day")
                .epoch_seconds(),
            1_709_164_800
        );
        assert_eq!(
            Timestamp::parse("1999-12-31T23:59:59Z")
                .expect("end of 1999")
                .epoch_seconds(),
            946_684_799
        );
    }

    #[test]
    fn fractional_seconds_are_truncated() {
        assert_eq!(
            Timestamp::parse("2000-01-01T00:00:00.999Z")
                .expect("fractional")
                .epoch_seconds(),
            946_684_800
        );
    }

    #[test]
    fn rejects_bad_timestamps() {
        assert!(Timestamp::parse("2023-02-29T00:00:00Z").is_err());
        assert!(Timestamp::parse("2027-01-01T00:00:00").is_err());
        assert!(Timestamp::parse("2027-01-01T00:00:00+01:00").is_err());
        assert!(Timestamp::parse("2027-00-01T00:00:00Z").is_err());
        assert!(Timestamp::parse("2027-01-01T24:00:00Z").is_err());
        assert!(Timestamp::parse("garbage").is_err());
    }

    #[test]
    fn human_principal_rule() {
        assert!(is_human_principal("human:alice"));
        assert!(is_human_principal("cfo@acme.example"));
        assert!(!is_human_principal("svc:bot"));
        assert!(!is_human_principal("service:orch"));
    }
}
