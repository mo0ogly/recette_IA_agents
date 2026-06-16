//! discoveryprobe-broker -- the only privilege-bearing component (CAP_BPF).
//!
//! Split so privilege is contained:
//! - [`manifest`], [`command`], [`audit`], [`handler`]: PURE logic
//!   (allowlist, deny-by-default validation, append-only audit I1,
//!   orchestration). Unit-tested without privilege.
//! - [`server`]: the Unix-socket front door that injects the REAL eBPF capture.
//!   Runs only under CAP_BPF.
//!
//! Contract (design §7): one parameterised command `capture { agents,
//! duration_ms }`, agents validated against the declared manifest
//! (deny-by-default), duration bounded, every run audited immutably (I1). The
//! API relays to the socket; the API never holds privilege. Launched by
//! ./recette.sh only (R19).

pub mod audit;
pub mod command;
pub mod handler;
pub mod manifest;
pub mod server;

pub use command::{validate, CaptureRequest, RejectReason, ValidatedCapture};
pub use handler::{handle, BrokerResponse};
pub use manifest::Manifest;
pub use server::{serve, ServerConfig};
