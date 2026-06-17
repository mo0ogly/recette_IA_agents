# discoveryprobe -- native discovery engine (Rust)

The Rust side of the discovery recette: a native eBPF reference probe plus the
source-side detectors that feed the Python judge (`recette/surface/`). Native by
design (R22): built with cargo on the host, never baked into the base Docker
image. The kernel program crate builds separately for `bpfel-unknown-none`.

## Crates

| Crate | Role | Privilege |
|-------|------|-----------|
| `discoveryprobe-common` | Wire structs shared kernel<->userspace (`ExecEvent`, `ConnectEvent`); `no_std`, zero deps, compiles for the eBPF target too | none |
| `discoveryprobe-core` | `CaptureRecording` / `ObservationSurface` -- the bridge contract whose JSON the Python surface judge consumes; deterministic (I4) | none |
| `discoveryprobe-capture` | `LlmCallTrace` + `CaptureSink` / `RingCaptureRecorder` (agenttrace field set + agentwatch callback mechanism, migrated to Rust) | none |
| `discoveryprobe-catalog` | Ingest a declarative agent-catalog registry index -> invariant `DiscoverySummary` (count/dedup/tool-coverage/tags); CLI | none |
| `discoveryprobe-detect` | Static "reperage" of agent-observability tooling (12 tools) by signature -> tool + category + evidence; CLI | none |
| `discoveryprobe` | Userspace loader: `probe` (privileged capture) + `mapping` (pure exec+connect -> recording) | CAP_BPF for `probe` |
| `discoveryprobe-broker` | Privileged capture daemon (unix socket 0600, deny-by-default, append-only audit + sha256) | CAP_BPF |
| `discoveryprobe-ebpf` | Kernel programs (`sched_process_exec`, `sys_enter_connect`); EXCLUDED from the host workspace, builds for `bpfel-unknown-none` | loaded under the broker |

## Shared sources of truth (no drift)

These committed files are the single source of truth, asserted by tests on BOTH
the Rust and Python sides so the two engines cannot diverge:

- `corpus/detect/observability-signatures.json` -- the 12-tool signature table
  (Rust static `SIGNATURES` == JSON, agreement test).
- `corpus/detect/agreement-cases.json` -- detector behaviour cases (Rust
  `detect` == Python `_detect`).
- `corpus/catalog/agent-registry.json` -- the catalog ground-truth subject.
- `discoveryprobe-core::ObservationSurface` serde names == `recette/surface/surfaces.py`.

## Build

```
cargo build --workspace            # host crates (cargo from this dir)
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

eBPF object (separate toolchain: nightly + rust-src + bpf-linker):

```
cd discoveryprobe-ebpf && cargo build --release   # -> bpfel-unknown-none object (readelf: Linux BPF)
```

Live capture (`discoveryprobe`/`discoveryprobe-broker`) needs `CAP_BPF` and runs
only under the broker; the pure `mapping` + the detectors are unit-tested without
privilege. Live proof: `scripts/smoke_discoveryprobe_broker.sh` (privileged
container). The recording -> judge bridge is `recette/surface/`.
