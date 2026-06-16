//! Recording contract for the discoveryprobe eBPF reference probe.
//!
//! The native probe observes a live simulated agent (syscalls / wire) and emits
//! a [`CaptureRecording`] per agent: the set of identifiers visible on each
//! observation surface. The Python surface-detection judge (`recette/surface/`)
//! consumes this recording, so the JSON shape here is the bridge contract.
//!
//! Determinism (I4): the recording stores observations in sorted, de-duplicated
//! order (a [`BTreeMap`] of surfaces, sorted `Vec` of keys), so the same capture
//! serialises byte-for-byte identically and the downstream judge stays
//! replay-stable. The probe captures live (non-deterministic timing); freezing
//! it into this normalised recording is what makes the judgement reproducible.

use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};

/// The surfaces RailNode can observe an agent on. The serialised names match
/// `recette/surface/surfaces.py::ObservationSurface` exactly (the bridge).
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ObservationSurface {
    /// In-process subprocess hook.
    HookSubprocess,
    /// In-process MCP / LSP tool-call interception.
    HookMcp,
    /// In-process SDK interception.
    HookSdk,
    /// Kernel eBPF / syscall + network capture.
    EbpfWire,
}

/// One agent's capture: what was visible on each surface during the window.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CaptureRecording {
    /// The simulated agent this recording belongs to.
    pub agent_id: String,
    /// Per-surface visible identifiers, sorted and de-duplicated (I4).
    pub surfaces: BTreeMap<ObservationSurface, Vec<String>>,
}

impl CaptureRecording {
    /// Build an empty recording for `agent_id`.
    pub fn new(agent_id: impl Into<String>) -> Self {
        Self {
            agent_id: agent_id.into(),
            surfaces: BTreeMap::new(),
        }
    }

    /// Record that `key` was observed on `surface`. Idempotent: a repeated
    /// observation does not change the recording (the set is de-duplicated).
    pub fn observe(&mut self, surface: ObservationSurface, key: impl Into<String>) {
        self.surfaces.entry(surface).or_default().push(key.into());
    }

    /// Normalise every surface's keys to a sorted, de-duplicated `Vec` (I4).
    /// Call once after all observations are recorded, before serialising.
    pub fn normalise(&mut self) {
        for keys in self.surfaces.values_mut() {
            let unique: BTreeSet<String> = keys.drain(..).collect();
            keys.extend(unique);
        }
    }

    /// Serialise to the bridge JSON the Python judge consumes. Normalises first,
    /// so the output is deterministic regardless of observation order.
    pub fn to_json(&self) -> Result<String, serde_json::Error> {
        let mut normalised = self.clone();
        normalised.normalise();
        serde_json::to_string(&normalised)
    }

    /// Parse a recording from the bridge JSON.
    pub fn from_json(raw: &str) -> Result<Self, serde_json::Error> {
        serde_json::from_str(raw)
    }

    /// True if the agent was visible on at least one surface -- the detection
    /// signal. An agent visible nowhere is the thesis failure (false negative).
    pub fn detected_anywhere(&self) -> bool {
        self.surfaces.values().any(|keys| !keys.is_empty())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn surface_serialises_to_the_python_name() {
        let json = serde_json::to_string(&ObservationSurface::EbpfWire).expect("serialise");
        assert_eq!(json, "\"ebpf_wire\"");
    }

    #[test]
    fn observe_records_a_key_on_a_surface() {
        let mut rec = CaptureRecording::new("pr-bot");
        rec.observe(ObservationSurface::HookSdk, "open_pr:acme/web#42");
        assert_eq!(
            rec.surfaces.get(&ObservationSurface::HookSdk),
            Some(&vec!["open_pr:acme/web#42".to_string()])
        );
    }

    #[test]
    fn normalise_sorts_and_deduplicates_keys() {
        let mut rec = CaptureRecording::new("ghost");
        rec.observe(ObservationSurface::EbpfWire, "POST b:443/2");
        rec.observe(ObservationSurface::EbpfWire, "POST a:443/1");
        rec.observe(ObservationSurface::EbpfWire, "POST a:443/1");
        rec.normalise();
        assert_eq!(
            rec.surfaces.get(&ObservationSurface::EbpfWire),
            Some(&vec![
                "POST a:443/1".to_string(),
                "POST b:443/2".to_string()
            ])
        );
    }

    #[test]
    fn to_json_is_deterministic_regardless_of_observation_order() {
        let mut a = CaptureRecording::new("x");
        a.observe(ObservationSurface::EbpfWire, "z");
        a.observe(ObservationSurface::HookSdk, "y");
        let mut b = CaptureRecording::new("x");
        b.observe(ObservationSurface::HookSdk, "y");
        b.observe(ObservationSurface::EbpfWire, "z");
        assert_eq!(a.to_json().expect("a"), b.to_json().expect("b"));
    }

    #[test]
    fn round_trips_through_json() {
        let mut rec = CaptureRecording::new("pr-bot");
        rec.observe(ObservationSurface::EbpfWire, "POST api.github.com:443/p");
        let json = rec.to_json().expect("to_json");
        let parsed = CaptureRecording::from_json(&json).expect("from_json");
        let mut expected = rec.clone();
        expected.normalise();
        assert_eq!(parsed, expected);
    }

    #[test]
    fn ghost_seen_only_on_wire_is_detected_anywhere() {
        let mut rec = CaptureRecording::new("ghost");
        rec.observe(ObservationSurface::EbpfWire, "POST shadow-db:5432/w");
        assert!(rec.detected_anywhere());
    }

    #[test]
    fn vanished_agent_is_not_detected_anywhere() {
        let rec = CaptureRecording::new("vanished");
        assert!(!rec.detected_anywhere());
    }
}
