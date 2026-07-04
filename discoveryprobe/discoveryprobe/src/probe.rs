//! Privileged capture: load + attach the eBPF program and drain its ring buffer.
//!
//! Uses the canonical aya idiom (aya `aya/src/maps/ring_buf.rs` doc example and
//! `TracePoint::load`/`attach`): load the object, get the tracepoint program,
//! `load()` + `attach(category, name)`, then poll `RingBuf::next` until the
//! bounded window elapses.
//!
//! PRIVILEGED: loading and attaching a BPF program requires CAP_BPF. This runs
//! only under the broker; the host `cargo test` exercises [`crate::mapping`],
//! not this path.

use std::path::PathBuf;
use std::time::{Duration, Instant};

use anyhow::{Context, Result};
use aya::maps::{MapData, RingBuf};
use aya::programs::TracePoint;
use aya::Ebpf;
use discoveryprobe_common::{
    AcceptEvent, ConnectEvent, DnsEvent, ExecEvent, FileEvent, ForkEvent, ListenEvent,
    UnixConnectEvent,
};
use discoveryprobe_core::ipc::IpcEvents;

/// The exec tracepoint the exec-capture program attaches to.
const EXEC_CATEGORY: &str = "sched";
const EXEC_NAME: &str = "sched_process_exec";
/// The connect tracepoint the egress-capture program attaches to.
const CONNECT_CATEGORY: &str = "syscalls";
const CONNECT_NAME: &str = "sys_enter_connect";
/// The fork tracepoint the process-tree program attaches to (same `sched`
/// category as exec).
const FORK_NAME: &str = "sched_process_fork";
/// The openat tracepoint the file-access program attaches to (same `syscalls`
/// category as connect).
const FILE_NAME: &str = "sys_enter_openat";
/// The sendto tracepoint the DNS-query program attaches to (same `syscalls`
/// category as connect).
const DNS_NAME: &str = "sys_enter_sendto";
/// The bind tracepoint the port-stash program attaches to (same `syscalls`
/// category as connect). Records pid->port; emits no ring event.
const BIND_NAME: &str = "sys_enter_bind";
/// The listen tracepoint the server-side program attaches to.
const LISTEN_NAME: &str = "sys_enter_listen";
/// The accept4 tracepoint the live-server program attaches to. The `sys_exit`
/// variant carries the return value, so a successful accept (ret >= 0) is
/// distinguishable from a failed one.
const ACCEPT_NAME: &str = "sys_exit_accept4";
/// The program and map symbols, matching `discoveryprobe-ebpf/src/main.rs`.
const EXEC_PROGRAM: &str = "discoveryprobe_exec";
const CONNECT_PROGRAM: &str = "discoveryprobe_connect";
const FORK_PROGRAM: &str = "discoveryprobe_fork";
const FILE_PROGRAM: &str = "discoveryprobe_openat";
const DNS_PROGRAM: &str = "discoveryprobe_sendto";
const BIND_PROGRAM: &str = "discoveryprobe_bind";
const LISTEN_PROGRAM: &str = "discoveryprobe_listen";
const ACCEPT_PROGRAM: &str = "discoveryprobe_accept4";
const EXEC_RING_MAP: &str = "EXEC_EVENTS";
const CONNECT_RING_MAP: &str = "CONNECT_EVENTS";
const FORK_RING_MAP: &str = "FORK_EVENTS";
const FILE_RING_MAP: &str = "FILE_EVENTS";
const DNS_RING_MAP: &str = "DNS_EVENTS";
const LISTEN_RING_MAP: &str = "LISTEN_EVENTS";
const ACCEPT_RING_MAP: &str = "ACCEPT_EVENTS";
const UNIX_CONNECT_RING_MAP: &str = "UNIX_CONNECT_EVENTS";

/// Where the compiled BPF object lives and how long to capture.
#[derive(Debug, Clone)]
pub struct CaptureConfig {
    /// Path to the `bpfel-unknown-none` object built by `discoveryprobe-ebpf`.
    pub object_path: PathBuf,
    /// Bounded capture window. Live capture is non-deterministic (I4 applies to
    /// the pure judge, not to this measurement).
    pub window: Duration,
}

/// One window of kernel observations: process execs and outbound connects.
///
/// The two surfaces of the kernel probe, captured together and reconciled into
/// a single `ebpf_wire` recording by [`crate::recordings_from_capture`].
#[derive(Debug, Clone, Default)]
pub struct Capture {
    /// Process-exec events (the agent ran).
    pub execs: Vec<ExecEvent>,
    /// Outbound TCP connect events (the agent dialed out, e.g. an LLM provider).
    pub connects: Vec<ConnectEvent>,
    /// Process fork (parent->child) edges, for process-tree attribution.
    pub forks: Vec<ForkEvent>,
    /// File-open events (the agent touched a file, the data-access surface).
    pub files: Vec<FileEvent>,
    /// DNS-query events (the agent resolved a name, the name-resolution surface).
    pub dns: Vec<DnsEvent>,
    /// TCP listen events (an agent serves a local port, the server side of an
    /// inter-agent edge).
    pub listens: Vec<ListenEvent>,
    /// TCP accept events (a live server actually took an inbound connection).
    pub accepts: Vec<AcceptEvent>,
    /// `AF_UNIX` connect events (a local IPC dial over a socket file).
    pub unix_connects: Vec<UnixConnectEvent>,
}

impl Capture {
    /// Reconcile the inter-agent communication captures (listen / accept /
    /// connect / unix-connect) into a normalised, deterministic [`IpcEvents`].
    ///
    /// The connect surface is REUSED here as the client side of a localhost
    /// edge. The mapping is pure (sorted, de-duplicated); it lives in
    /// `discoveryprobe-core::ipc` and is unit-tested without privilege.
    pub fn ipc_events(&self) -> IpcEvents {
        IpcEvents::from_events(
            &self.listens,
            &self.accepts,
            &self.connects,
            &self.unix_connects,
        )
    }
}

/// Load + attach both capture programs and collect their events for the window.
///
/// PRIVILEGED (CAP_BPF). Returns every [`ExecEvent`] and [`ConnectEvent`] the
/// kernel reported during the window, in capture order; the pure
/// [`crate::mapping`] turns them into replay-stable recordings.
pub fn capture(config: &CaptureConfig) -> Result<Capture> {
    let mut session = Session::attach(&config.object_path)?;
    let deadline = Instant::now() + config.window;
    let mut capture = Capture::default();
    loop {
        let slice = session.drain();
        capture.execs.extend(slice.execs);
        capture.connects.extend(slice.connects);
        capture.forks.extend(slice.forks);
        capture.files.extend(slice.files);
        capture.dns.extend(slice.dns);
        capture.listens.extend(slice.listens);
        capture.accepts.extend(slice.accepts);
        capture.unix_connects.extend(slice.unix_connects);
        if Instant::now() >= deadline {
            break;
        }
        // The kernel ring buffer retains events between drains, so a short tick
        // within the bounded window loses nothing and needs no async runtime.
        std::thread::sleep(Duration::from_millis(5));
    }
    Ok(capture)
}

/// A LIVE attached probe: the tracepoints stay attached for the session's life,
/// so draining periodically loses nothing between drains (the kernel ring
/// buffers events). This is the gap-free basis of the passive `watch` stream --
/// unlike repeated [`capture`] calls, which re-attach (and miss events between
/// windows). PRIVILEGED (CAP_BPF). Stays attached until dropped.
pub struct Session {
    // `_bpf` MUST outlive the rings/programs: dropping it detaches the probe.
    _bpf: Ebpf,
    exec_ring: RingBuf<MapData>,
    connect_ring: RingBuf<MapData>,
    fork_ring: RingBuf<MapData>,
    file_ring: RingBuf<MapData>,
    dns_ring: RingBuf<MapData>,
    listen_ring: RingBuf<MapData>,
    accept_ring: RingBuf<MapData>,
    unix_connect_ring: RingBuf<MapData>,
}

impl Session {
    /// Load the object and attach both tracepoints once.
    pub fn attach(object_path: &std::path::Path) -> Result<Self> {
        let object = std::fs::read(object_path)
            .with_context(|| format!("read bpf object {}", object_path.display()))?;
        let mut bpf = Ebpf::load(&object).context("load bpf object")?;
        attach_tracepoint(&mut bpf, EXEC_PROGRAM, EXEC_CATEGORY, EXEC_NAME)?;
        attach_tracepoint(&mut bpf, CONNECT_PROGRAM, CONNECT_CATEGORY, CONNECT_NAME)?;
        attach_tracepoint(&mut bpf, FORK_PROGRAM, EXEC_CATEGORY, FORK_NAME)?;
        attach_tracepoint(&mut bpf, FILE_PROGRAM, CONNECT_CATEGORY, FILE_NAME)?;
        attach_tracepoint(&mut bpf, DNS_PROGRAM, CONNECT_CATEGORY, DNS_NAME)?;
        // The inter-agent comm surface (Task 9): bind stashes pid->port (no ring),
        // listen/accept4 emit the server side, and the connect program above also
        // emits AF_UNIX dials into UNIX_CONNECT_EVENTS. All share the `syscalls`
        // category.
        attach_tracepoint(&mut bpf, BIND_PROGRAM, CONNECT_CATEGORY, BIND_NAME)?;
        attach_tracepoint(&mut bpf, LISTEN_PROGRAM, CONNECT_CATEGORY, LISTEN_NAME)?;
        attach_tracepoint(&mut bpf, ACCEPT_PROGRAM, CONNECT_CATEGORY, ACCEPT_NAME)?;
        let exec_ring = take_ring(&mut bpf, EXEC_RING_MAP)?;
        let connect_ring = take_ring(&mut bpf, CONNECT_RING_MAP)?;
        let fork_ring = take_ring(&mut bpf, FORK_RING_MAP)?;
        let file_ring = take_ring(&mut bpf, FILE_RING_MAP)?;
        let dns_ring = take_ring(&mut bpf, DNS_RING_MAP)?;
        let listen_ring = take_ring(&mut bpf, LISTEN_RING_MAP)?;
        let accept_ring = take_ring(&mut bpf, ACCEPT_RING_MAP)?;
        let unix_connect_ring = take_ring(&mut bpf, UNIX_CONNECT_RING_MAP)?;
        Ok(Self {
            _bpf: bpf,
            exec_ring,
            connect_ring,
            fork_ring,
            file_ring,
            dns_ring,
            listen_ring,
            accept_ring,
            unix_connect_ring,
        })
    }

    /// Drain everything currently buffered in both rings (non-blocking).
    pub fn drain(&mut self) -> Capture {
        let mut capture = Capture::default();
        while let Some(item) = self.exec_ring.next() {
            if let Some(event) = ExecEvent::from_bytes(&item) {
                capture.execs.push(event);
            }
        }
        while let Some(item) = self.connect_ring.next() {
            if let Some(event) = ConnectEvent::from_bytes(&item) {
                capture.connects.push(event);
            }
        }
        while let Some(item) = self.fork_ring.next() {
            if let Some(event) = ForkEvent::from_bytes(&item) {
                capture.forks.push(event);
            }
        }
        while let Some(item) = self.file_ring.next() {
            if let Some(event) = FileEvent::from_bytes(&item) {
                capture.files.push(event);
            }
        }
        while let Some(item) = self.dns_ring.next() {
            if let Some(event) = DnsEvent::from_bytes(&item) {
                capture.dns.push(event);
            }
        }
        while let Some(item) = self.listen_ring.next() {
            if let Some(event) = ListenEvent::from_bytes(&item) {
                capture.listens.push(event);
            }
        }
        while let Some(item) = self.accept_ring.next() {
            if let Some(event) = AcceptEvent::from_bytes(&item) {
                capture.accepts.push(event);
            }
        }
        while let Some(item) = self.unix_connect_ring.next() {
            if let Some(event) = UnixConnectEvent::from_bytes(&item) {
                capture.unix_connects.push(event);
            }
        }
        capture
    }
}

/// Load and attach one tracepoint program by symbol/category/name.
fn attach_tracepoint(bpf: &mut Ebpf, program: &str, category: &str, name: &str) -> Result<()> {
    let prog: &mut TracePoint = bpf
        .program_mut(program)
        .with_context(|| format!("program {program} not found in object"))?
        .try_into()
        .with_context(|| format!("{program} is not a tracepoint"))?;
    prog.load()
        .with_context(|| format!("load tracepoint program {program}"))?;
    prog.attach(category, name)
        .with_context(|| format!("attach {category}:{name}"))?;
    Ok(())
}

/// Take ownership of a ring-buffer map out of the loaded object.
fn take_ring(bpf: &mut Ebpf, name: &str) -> Result<RingBuf<MapData>> {
    let map = bpf
        .take_map(name)
        .with_context(|| format!("map {name} not found in object"))?;
    RingBuf::try_from(map).with_context(|| format!("open ring buffer {name}"))
}
