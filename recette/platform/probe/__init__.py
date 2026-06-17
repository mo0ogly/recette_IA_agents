"""Probe-side helpers: the replay broker that stands in for the privileged eBPF
broker when no CAP_BPF is available (dev / CI).

The native ``discoveryprobe-broker`` (Rust, CAP_BPF) is the only component that
loads eBPF and produces a LIVE capture. Where that privilege is absent, the
replay broker serves a deterministic REPLAY of known-captured surface state,
derived from the committed ``corpus/surface`` ground-truth, over the exact same
Unix-socket wire form the API relay speaks. It is explicitly a replay (mode
``replay``), never a fabricated live capture (R13/R14): the live eBPF proof
remains the broker's job.
"""
