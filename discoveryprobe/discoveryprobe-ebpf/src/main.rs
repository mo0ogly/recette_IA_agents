#![no_std]
#![no_main]

//! discoveryprobe eBPF capture program.
//!
//! Attaches to the `sched:sched_process_exec` tracepoint (more stable across
//! kernel versions than the raw `execve` syscall tracepoint). For every process
//! exec it captures the pid and command name -- the kernel's evidence that an
//! agent process is running -- and pushes one [`ExecEvent`] into a ring buffer
//! the userspace loader drains. Because the host kernel sees every container's
//! processes (one shared kernel), this captures a Dockerised simulated agent
//! without any in-process hook: the eBPF-wire surface.
//!
//! Privilege: this program only RUNS once loaded and attached by the privileged
//! broker (CAP_BPF). Compiling it (what this crate proves unprivileged) does not
//! load or attach anything.

use aya_ebpf::{
    helpers::{
        bpf_get_current_comm, bpf_get_current_pid_tgid, bpf_probe_read_user,
        bpf_probe_read_user_str_bytes,
    },
    macros::{map, tracepoint},
    maps::{HashMap, RingBuf},
    programs::TracePointContext,
};
use discoveryprobe_common::{
    AcceptEvent, ConnectEvent, DnsEvent, ExecEvent, FileEvent, ForkEvent, ListenEvent,
    UnixConnectEvent, PATH_LEN, QNAME_LEN, UNIX_PATH_LEN,
};

/// Ring buffer the userspace loader drains (256 KiB: power-of-two page multiple).
#[map]
static EXEC_EVENTS: RingBuf = RingBuf::with_byte_size(256 * 1024, 0);

/// Ring buffer for outbound connect events, drained by the same loader.
#[map]
static CONNECT_EVENTS: RingBuf = RingBuf::with_byte_size(256 * 1024, 0);

/// Ring buffer for process fork (parent->child) edges, drained by the same loader.
#[map]
static FORK_EVENTS: RingBuf = RingBuf::with_byte_size(256 * 1024, 0);

/// Ring buffer for file-open events, drained by the same loader. `openat` is a
/// very high-frequency syscall (every shared-library load, config read, etc.),
/// so this ring can see heavy traffic; the capture is passive (drops on a full
/// ring) and the userspace mapping filters to the attributed pids, so the
/// RECORDING stays clean. A pid-allowlist eBPF filter (drop events from
/// non-agent pids in-kernel) is a possible later optimization, not built here.
#[map]
static FILE_EVENTS: RingBuf = RingBuf::with_byte_size(256 * 1024, 0);

/// Ring buffer for DNS-query events, drained by the same loader. `sendto` is a
/// high-frequency syscall, but `try_capture_dns` gates HARD on UDP destination
/// port 53 before doing any work, so only actual DNS queries reach the ring;
/// the capture is passive (drops on a full ring) and the userspace mapping
/// filters to the attributed pids.
#[map]
static DNS_EVENTS: RingBuf = RingBuf::with_byte_size(256 * 1024, 0);

/// Ring buffer for TCP listen events (the server side of an inter-agent edge),
/// drained by the same loader. Emitted at `listen`, correlated to the port the
/// pid recorded at `bind` (see [`BIND_PORTS`]).
#[map]
static LISTEN_EVENTS: RingBuf = RingBuf::with_byte_size(256 * 1024, 0);

/// Ring buffer for TCP accept events (a live server actually took a connection),
/// drained by the same loader.
#[map]
static ACCEPT_EVENTS: RingBuf = RingBuf::with_byte_size(256 * 1024, 0);

/// Ring buffer for `AF_UNIX` connect events (local IPC dial over a socket file,
/// invisible to TCP-only capture), drained by the same loader.
#[map]
static UNIX_CONNECT_EVENTS: RingBuf = RingBuf::with_byte_size(256 * 1024, 0);

/// pid -> bound TCP port (network-order bytes held as a `u16`). `bind` carries
/// the address but `listen` does not, so the port observed at `bind` is stashed
/// here keyed by pid and read back when the same pid calls `listen`. Bounded to
/// a fixed capacity so the map cannot grow without limit (passive: an insert
/// into a full map fails silently and the listen simply emits nothing).
///
/// **Completeness boundary:** The map is keyed by pid alone, so a multi-port server
/// (multiple binds on the same pid) emits a ListenEvent only for the last-bound port.
///
/// AF_UNIX binds are NOT recorded here -- the Unix server side is inferred downstream
/// from a [`UnixConnectEvent`] path match, keeping this path simple.
#[map]
static BIND_PORTS: HashMap<u32, u16> = HashMap::with_max_entries(MAX_BIND_ENTRIES, 0);

/// Bounded capacity of [`BIND_PORTS`] (a fixed upper bound on tracked binders).
const MAX_BIND_ENTRIES: u32 = 4096;

/// `AF_UNIX` -- local IPC socket family (server/client over a socket file).
const AF_UNIX: u16 = 1;

/// Byte offset of the `struct sockaddr * umyaddr` argument in the
/// `syscalls:sys_enter_bind` tracepoint record. Stable syscall-enter layout:
/// common header `0..8`, `__syscall_nr` at `8`, then args from `16` (fd@16,
/// umyaddr@24, addrlen@32) -- the second argument, same slot as connect's
/// `uservaddr`. This is the standard sys_enter_bind field layout, to be
/// empirically validated by the live capture (the verified `format` dump is the
/// source of truth, see docs/migration-provenance.md).
const BIND_UMYADDR_OFFSET: usize = 24;

/// Byte offset of the `long ret` field in the `syscalls:sys_exit_accept4`
/// tracepoint record. Stable syscall-exit layout: common header `0..8`,
/// `__syscall_nr` at `8`, then `ret` at `16`. A non-negative `ret` is the new
/// connection fd (accept succeeded); a negative `ret` is an error and is
/// dropped, so an [`AcceptEvent`] means the pid actually took an inbound
/// connection. To be empirically validated by the live capture (the verified
/// `format` dump is the source of truth, see docs/migration-provenance.md).
const ACCEPT_RET_OFFSET: usize = 16;

/// Byte offset of the `sockaddr_un.sun_path` char array within a `struct
/// sockaddr_un`: `sun_family` is a `u16` at `0`, so `sun_path` begins at `2`.
const SUN_PATH_OFFSET: usize = 2;

/// Byte offsets of the `parent_pid` / `child_pid` fields in the
/// `sched:sched_process_fork` tracepoint record. Standard layout: common header
/// `0..8`, then `parent_comm[16]`@8, `parent_pid`@24, `child_comm[16]`@28,
/// `child_pid`@44. These are the standard sched_process_fork field offsets, to
/// be empirically validated by the live capture (a wrong offset makes
/// attribution fail -- never a fake; the verified `format` dump is the source of
/// truth, see docs/migration-provenance.md).
const PARENT_PID_OFFSET: usize = 24;
const CHILD_PID_OFFSET: usize = 44;

/// `AF_INET` -- IPv4 socket family (the only family captured for now).
const AF_INET: u16 = 2;

/// Byte offset of the `struct sockaddr * uservaddr` argument in the
/// `syscalls:sys_enter_connect` tracepoint record. Stable syscall-enter layout:
/// common header `0..8`, `__syscall_nr` at `8`, then args from `16` (fd@16,
/// uservaddr@24, addrlen@32). Verified against the kernel tracepoint `format`
/// (root-gated on this host); see docs/migration-provenance.md for the source.
const USERVADDR_OFFSET: usize = 24;

/// Byte offset of the `filename` (user `const char *`) argument in the
/// `syscalls:sys_enter_openat` tracepoint record. Standard syscall-enter
/// layout: common header `0..8`, `__syscall_nr` at `8`, then args from `16`
/// (dfd@16, filename(ptr)@24, flags@32, mode@40). This is the standard
/// sys_enter_openat field layout, to be empirically validated by the live
/// capture (a wrong offset reads a garbage pointer and the user-string read
/// fails -- never a fake; the verified `format` dump is the source of truth,
/// see docs/migration-provenance.md).
const OPENAT_FILENAME_OFFSET: usize = 24;

/// Byte offsets of the `buff` (user payload `const void *`) and `addr` (user
/// `struct sockaddr *`) arguments in the `syscalls:sys_enter_sendto` tracepoint
/// record. Standard syscall-enter layout: common header `0..8`, `__syscall_nr`
/// at `8`, then args from `16` (fd@16, buff(ptr)@24, len@32, flags@40,
/// addr(ptr)@48, addr_len@56). These are the standard sys_enter_sendto field
/// offsets, to be empirically validated by the live capture (a wrong offset
/// reads a garbage pointer and the user read fails -- never a fake; the verified
/// `format` dump is the source of truth, see docs/migration-provenance.md).
const SENDTO_BUFF_OFFSET: usize = 24;
const SENDTO_ADDR_OFFSET: usize = 48;

/// DNS server port (53) in network byte order: the two `sin_port` bytes the
/// kernel holds for a query to port 53 are `[0x00, 0x35]`, i.e. the big-endian
/// u16 `53`. We compare the raw big-endian value (mirrors the connect probe's
/// `to_ne_bytes` handling: the bytes are kept in network order).
const DNS_PORT_BE: u16 = 53u16.to_be();

/// DNS message header length (12 bytes: id, flags, qdcount, ancount, nscount,
/// arcount) before the QNAME labels begin.
const DNS_HEADER_LEN: usize = 12;

/// Maximum number of payload bytes the QNAME parse will walk in its single
/// fixed-trip loop. A constant so the verifier sees a fixed loop bound; 128
/// bytes covers realistic hostnames (a DNS name is at most 253 bytes, but real
/// API/agent hosts are far shorter), and a longer name is simply truncated
/// (passive). Kept small enough that the flat parse stays well under the
/// verifier instruction budget on a strict (kernel 6.17) verifier.
const MAX_QNAME_BYTES: usize = 128;

/// Maximum bytes of a single DNS label per the RFC (a length byte is 6 bits of
/// length when the top two bits are 0). A length byte above this is a
/// compression pointer or malformed, and stops the parse.
const MAX_LABEL_LEN: usize = 63;

#[tracepoint]
pub fn discoveryprobe_exec(ctx: TracePointContext) -> u32 {
    // A failed capture (full ring buffer, comm read error) drops the event
    // rather than disturbing the traced process -- the probe is passive.
    let _ = try_capture(&ctx);
    0
}

fn try_capture(_ctx: &TracePointContext) -> Result<(), ()> {
    // Do every FALLIBLE step BEFORE reserving the ring entry. A reserved entry
    // must be submitted or discarded on every path; bailing out (`?`) after a
    // reserve leaks the reference and the verifier rejects the program
    // ("Unreleased reference ... BPF_EXIT would lead to reference leak"). So
    // read pid + comm first, then reserve and UNCONDITIONALLY write + submit.
    let pid = (bpf_get_current_pid_tgid() >> 32) as u32;
    let comm = bpf_get_current_comm().map_err(|_| ())?;
    let mut entry = EXEC_EVENTS.reserve::<ExecEvent>(0).ok_or(())?;
    entry.write(ExecEvent { pid, comm });
    entry.submit(0);
    Ok(())
}

#[tracepoint]
pub fn discoveryprobe_connect(ctx: TracePointContext) -> u32 {
    // Passive: any read/reserve failure drops the event, never disturbs the
    // traced process.
    let _ = try_capture_connect(&ctx);
    0
}

fn try_capture_connect(ctx: &TracePointContext) -> Result<(), i64> {
    // The agent's outbound connect. For an LLM agent over TCP: the HTTPS dial to
    // the provider (agentwatch sees this in-process at httpcore; here we see it
    // at the kernel, without the agent's cooperation -- catches a hook-blind
    // ghost). For a co-located agent mesh over AF_UNIX: the local IPC dial, which
    // TCP-only capture would miss entirely. Read the userspace `sockaddr` pointer
    // from the tracepoint record, then dispatch on the address family. One
    // tracepoint, two surfaces; each branch does its fallible reads BEFORE
    // reserving a ring entry (a reserved entry must be submitted on every path,
    // or the verifier rejects the program for a reference leak).
    // SAFETY: `read_at` reads a fixed-size pointer field at a verifier-checked
    // offset within the tracepoint record the kernel itself populated; the
    // offset is within the record bounds for sys_enter_connect.
    let uservaddr = unsafe { ctx.read_at::<*const u8>(USERVADDR_OFFSET)? };
    if uservaddr.is_null() {
        return Err(0);
    }
    // sockaddr layout begins with the family: sa_family_t u16 @0.
    // SAFETY: `bpf_probe_read_user` is the kernel-sanctioned fallible read of
    // userspace memory from an eBPF program -- a bad/unmapped address returns
    // Err (propagated by `?`) instead of faulting, so dereferencing the user
    // `sockaddr` pointer is sound.
    let family = unsafe { bpf_probe_read_user::<u16>(uservaddr as *const u16)? };
    match family {
        AF_INET => {
            // sockaddr_in: sin_port u16 (network order) @2, sin_addr u32 @4.
            // SAFETY: fallible userspace read at the sin_port (+2) offset within
            // the sockaddr_in; an out-of-bounds read returns Err.
            let port =
                unsafe { bpf_probe_read_user::<u16>(uservaddr.wrapping_add(2) as *const u16)? };
            // SAFETY: fallible userspace read at the sin_addr (+4) offset.
            let addr =
                unsafe { bpf_probe_read_user::<u32>(uservaddr.wrapping_add(4) as *const u32)? };

            let pid = (bpf_get_current_pid_tgid() >> 32) as u32;
            let comm = bpf_get_current_comm()?;

            let mut entry = CONNECT_EVENTS.reserve::<ConnectEvent>(0).ok_or(0_i64)?;
            // `to_ne_bytes` preserves the exact in-memory (network-order) bytes
            // the kernel read, so userspace parses octets in order and the port
            // big-endian.
            entry.write(ConnectEvent {
                pid,
                daddr: addr.to_ne_bytes(),
                dport: port.to_ne_bytes(),
                _pad: [0_u8; 2],
                comm,
            });
            entry.submit(0);
            Ok(())
        }
        AF_UNIX => {
            // sockaddr_un: sun_path char[108] @2. The path length (UNIX_PATH_LEN
            // = 108) is NOT a power of two, so the QNAME `& (LEN-1)` mask trick
            // does not apply; instead use the kernel bounded-string helper (the
            // same primitive the openat path uses for the file path). It copies
            // at most `path.len()` bytes, NUL-terminated, and never reads past
            // the fixed-size destination, which is exactly what the verifier
            // needs to bound the read -- no manual masking required.
            let mut path = [0_u8; UNIX_PATH_LEN];
            // SAFETY: `bpf_probe_read_user_str_bytes` is the kernel-sanctioned
            // bounded read of a NUL-terminated userspace string from an eBPF
            // program; a bad/unmapped address returns Err (propagated by `?`)
            // instead of faulting, and it writes at most `path.len()` bytes.
            let _ = unsafe {
                bpf_probe_read_user_str_bytes(uservaddr.wrapping_add(SUN_PATH_OFFSET), &mut path)?
            };

            let pid = (bpf_get_current_pid_tgid() >> 32) as u32;
            let comm = bpf_get_current_comm()?;

            let mut entry = UNIX_CONNECT_EVENTS
                .reserve::<UnixConnectEvent>(0)
                .ok_or(0_i64)?;
            // `path` is zero-initialised, so bytes past the read stay NUL: the
            // buffer is the truncated, NUL-padded socket path userspace reads.
            entry.write(UnixConnectEvent { pid, comm, path });
            entry.submit(0);
            Ok(())
        }
        // Other families (AF_INET6, ...) are dropped (documented boundary).
        _ => Err(0),
    }
}

#[tracepoint]
pub fn discoveryprobe_fork(ctx: TracePointContext) -> u32 {
    // Passive: any read/reserve failure drops the event, never disturbs the
    // traced process.
    let _ = try_capture_fork(&ctx);
    0
}

fn try_capture_fork(ctx: &TracePointContext) -> Result<(), i64> {
    // Learn the parent->child process edge so the userspace mapping can
    // attribute a child's exec/connect to the agent that owns the parent pid
    // (the process-tree view; a multi-process agent is not a blind spot).
    // Do every FALLIBLE read BEFORE reserving the ring entry: a reserved entry
    // must be submitted on every path, or the verifier rejects the program for
    // a reference leak.
    // SAFETY: `read_at` reads a fixed-size field at a verifier-checked offset
    // within the tracepoint record the kernel itself populated; both offsets are
    // within the record bounds for sched_process_fork.
    let parent_pid = unsafe { ctx.read_at::<u32>(PARENT_PID_OFFSET)? };
    let child_pid = unsafe { ctx.read_at::<u32>(CHILD_PID_OFFSET)? };

    let mut entry = FORK_EVENTS.reserve::<ForkEvent>(0).ok_or(0_i64)?;
    entry.write(ForkEvent {
        parent_pid,
        child_pid,
    });
    entry.submit(0);
    Ok(())
}

#[tracepoint]
pub fn discoveryprobe_openat(ctx: TracePointContext) -> u32 {
    // Passive: any read/reserve failure drops the event, never disturbs the
    // traced process.
    let _ = try_capture_openat(&ctx);
    0
}

fn try_capture_openat(ctx: &TracePointContext) -> Result<(), i64> {
    // The agent's file access -- which files it touches, the data-access surface
    // visible at the kernel WITHOUT the agent's cooperation. Read the userspace
    // `filename` pointer from the tracepoint record, then read the NUL-terminated
    // user string into a bounded buffer.
    // Do every FALLIBLE read BEFORE reserving the ring entry: a reserved entry
    // must be submitted on every path, or the verifier rejects the program for a
    // reference leak.
    // SAFETY: `read_at` reads a fixed-size pointer field at a verifier-checked
    // offset within the tracepoint record the kernel itself populated; the offset
    // is within the record bounds for sys_enter_openat.
    let filename = unsafe { ctx.read_at::<*const u8>(OPENAT_FILENAME_OFFSET)? };
    if filename.is_null() {
        return Err(0);
    }
    let mut path = [0_u8; PATH_LEN];
    // SAFETY: `bpf_probe_read_user_str_bytes` is the kernel-sanctioned bounded
    // read of a NUL-terminated userspace string from an eBPF program; a
    // bad/unmapped address returns Err (propagated by `?`) instead of faulting.
    // It writes at most `path.len()` bytes and never reads past the buffer.
    let read = unsafe { bpf_probe_read_user_str_bytes(filename, &mut path)? };
    // `path` is zero-initialised, so the bytes past `read.len()` stay NUL: the
    // buffer is the truncated, NUL-padded path the userspace side reads back.
    let _ = read;

    let pid = (bpf_get_current_pid_tgid() >> 32) as u32;
    let comm = bpf_get_current_comm()?;

    let mut entry = FILE_EVENTS.reserve::<FileEvent>(0).ok_or(0_i64)?;
    entry.write(FileEvent { pid, comm, path });
    entry.submit(0);
    Ok(())
}

#[tracepoint]
pub fn discoveryprobe_sendto(ctx: TracePointContext) -> u32 {
    // Passive: any read/reserve failure (or a non-DNS packet) drops the event,
    // never disturbs the traced process.
    let _ = try_capture_dns(&ctx);
    0
}

fn try_capture_dns(ctx: &TracePointContext) -> Result<(), i64> {
    // The agent's DNS query -- the name resolution that precedes the HTTPS dial
    // captured by the connect probe. Gate HARD on the destination being an
    // AF_INET UDP packet to port 53 before parsing anything, so non-DNS sendto
    // traffic costs only three reads. Then parse the QNAME labels from the DNS
    // payload into a dotted name. Do every FALLIBLE read BEFORE reserving the
    // ring entry: a reserved entry must be submitted on every path, or the
    // verifier rejects the program for a reference leak.

    // 1. Destination sockaddr gate: family must be AF_INET and port must be 53.
    // SAFETY: `read_at` reads a fixed-size pointer field at a verifier-checked
    // offset within the tracepoint record the kernel itself populated; the
    // offset is within the record bounds for sys_enter_sendto.
    let addr = unsafe { ctx.read_at::<*const u8>(SENDTO_ADDR_OFFSET)? };
    if addr.is_null() {
        return Err(0);
    }
    // sockaddr_in: sin_family u16 @0, sin_port u16 (network order) @2.
    // SAFETY: `bpf_probe_read_user` is the kernel-sanctioned fallible read of
    // userspace memory from an eBPF program -- a bad/unmapped address returns
    // Err (propagated by `?`) instead of faulting.
    let family = unsafe { bpf_probe_read_user::<u16>(addr as *const u16)? };
    if family != AF_INET {
        return Err(0);
    }
    // SAFETY: same -- a fallible userspace read at the sin_port (+2) offset.
    let port = unsafe { bpf_probe_read_user::<u16>(addr.wrapping_add(2) as *const u16)? };
    if port != DNS_PORT_BE {
        return Err(0);
    }

    // 2. Read the DNS payload pointer; the QNAME labels start after the header.
    // SAFETY: fixed-size pointer field at a verifier-checked offset in the record.
    let buff = unsafe { ctx.read_at::<*const u8>(SENDTO_BUFF_OFFSET)? };
    if buff.is_null() {
        return Err(0);
    }

    // 3. Walk the length-prefixed labels into a dotted name with a SINGLE
    // fixed-trip loop over the payload bytes. The payload offset is the loop
    // index plus the header length (`DNS_HEADER_LEN + i`), so the walk advances
    // exactly one byte per iteration. This flat form keeps the verifier state
    // small: the earlier nested form (outer label loop x inner copy loop, with a
    // running `out_len` accumulator and four break points) exploded to >1M
    // instructions / ~20k states on the kernel 6.17 verifier and the program was
    // rejected ("BPF program is too large"). One loop, one branch on
    // `label_remaining`, removes that combinatorial blow-up while preserving the
    // dotted-name output and the passive-truncation semantics.
    //
    // `out_len` index is masked with `& (QNAME_LEN - 1)` (QNAME_LEN is a power
    // of two) so every write is provably inside `qname`. The trip count
    // `MAX_QNAME_BYTES` bounds the payload walk to a small constant; a longer
    // name is simply truncated (passive).
    let mut qname = [0u8; QNAME_LEN];
    let mut out_len: usize = 0;
    // Bytes still to copy in the current label; 0 means the next byte read is a
    // length byte (the start of a new label).
    let mut label_remaining: usize = 0;
    let mut parsed_any = false;

    for i in 0..MAX_QNAME_BYTES {
        if out_len >= QNAME_LEN - 1 {
            // Leave room for the trailing NUL.
            break;
        }
        // SAFETY: fallible userspace read at a constant-bounded offset: the
        // index `i` is bounded by MAX_QNAME_BYTES, so the offset stays within
        // DNS_HEADER_LEN + MAX_QNAME_BYTES.
        let payload_off = DNS_HEADER_LEN + i;
        let byte = unsafe { bpf_probe_read_user::<u8>(buff.wrapping_add(payload_off))? };

        if label_remaining == 0 {
            // `byte` is a label-length byte.
            if byte == 0 {
                // Root label: end of QNAME.
                break;
            }
            if byte as usize > MAX_LABEL_LEN {
                // Compression pointer (top bits set) or malformed length: stop.
                break;
            }
            if parsed_any {
                // Separator between labels. Mask the index to a constant bound.
                let idx = out_len & (QNAME_LEN - 1);
                qname[idx] = b'.';
                out_len += 1;
            }
            label_remaining = byte as usize;
            parsed_any = true;
        } else {
            // `byte` is a label content byte. Mask the index to a constant bound.
            let idx = out_len & (QNAME_LEN - 1);
            qname[idx] = byte;
            out_len += 1;
            label_remaining -= 1;
        }
    }

    if !parsed_any {
        // No label parsed (empty/garbage payload): nothing to record.
        return Err(0);
    }

    let pid = (bpf_get_current_pid_tgid() >> 32) as u32;
    let comm = bpf_get_current_comm()?;

    let mut entry = DNS_EVENTS.reserve::<DnsEvent>(0).ok_or(0_i64)?;
    // `qname` is zero-initialised, so bytes past `out_len` stay NUL: userspace
    // reads the truncated, NUL-padded dotted name back.
    entry.write(DnsEvent { pid, comm, qname });
    entry.submit(0);
    Ok(())
}

#[tracepoint]
pub fn discoveryprobe_bind(ctx: TracePointContext) -> u32 {
    // Passive: any read/insert failure drops the record, never disturbs the
    // traced process.
    let _ = try_capture_bind(&ctx);
    0
}

fn try_capture_bind(ctx: &TracePointContext) -> Result<(), i64> {
    // `bind` carries the local address; `listen` does not. Stash the bound TCP
    // port keyed by pid so the subsequent `listen` from the same pid can emit a
    // ListenEvent with the port. This program writes only to the pid-keyed map
    // (no ring entry), so there is no reserve/submit reference to manage.
    // SAFETY: `read_at` reads a fixed-size pointer field at a verifier-checked
    // offset within the tracepoint record the kernel itself populated; the offset
    // is within the record bounds for sys_enter_bind.
    let umyaddr = unsafe { ctx.read_at::<*const u8>(BIND_UMYADDR_OFFSET)? };
    if umyaddr.is_null() {
        return Err(0);
    }
    // SAFETY: fallible userspace read of the sockaddr family (u16 @0); a
    // bad/unmapped address returns Err instead of faulting.
    let family = unsafe { bpf_probe_read_user::<u16>(umyaddr as *const u16)? };
    if family != AF_INET {
        // AF_UNIX server side is inferred downstream from a UnixConnectEvent path
        // match, not recorded here (documented simplification).
        return Err(0);
    }
    // sockaddr_in: sin_port u16 (network order) @2.
    // SAFETY: fallible userspace read at the sin_port (+2) offset.
    let port = unsafe { bpf_probe_read_user::<u16>(umyaddr.wrapping_add(2) as *const u16)? };
    let pid = (bpf_get_current_pid_tgid() >> 32) as u32;
    // Insert may fail if the bounded map is full; that is passive (the listen
    // just emits nothing), so propagate without disturbing the process.
    BIND_PORTS.insert(&pid, &port, 0).map_err(|_| 0_i64)?;
    Ok(())
}

#[tracepoint]
pub fn discoveryprobe_listen(ctx: TracePointContext) -> u32 {
    // Passive: any read/reserve failure drops the event, never disturbs the
    // traced process.
    let _ = try_capture_listen(&ctx);
    0
}

fn try_capture_listen(_ctx: &TracePointContext) -> Result<(), i64> {
    // The server side of an inter-agent edge: a pid moving a bound socket into
    // the listening state. Look up the port the pid recorded at `bind` (listen's
    // args carry no address). No recorded bind => nothing to emit (e.g. an
    // AF_UNIX bind, or a bind that fell out of the bounded map). Do the fallible
    // reads BEFORE reserving the ring entry (reference-leak rule).
    let pid = (bpf_get_current_pid_tgid() >> 32) as u32;
    // SAFETY: `get` reads the value for `pid` from the pid-keyed map; the value
    // is a plain `Copy` u16 that is immediately copied out (no borrow held across
    // the reserve), so the map-aliasing caveat on `get` does not apply.
    let port = match unsafe { BIND_PORTS.get(&pid) } {
        Some(port) => *port,
        None => return Err(0),
    };
    // Evict the entry to prevent the bounded map from filling up over a long
    // capture window. A failed remove is passive (just continue).
    let _ = BIND_PORTS.remove(&pid).map_err(|_| ());

    let comm = bpf_get_current_comm()?;

    let mut entry = LISTEN_EVENTS.reserve::<ListenEvent>(0).ok_or(0_i64)?;
    // `to_ne_bytes` preserves the exact network-order bytes read at bind, so
    // userspace reads the port big-endian (mirrors ConnectEvent::dport).
    entry.write(ListenEvent {
        pid,
        port: port.to_ne_bytes(),
        _pad: [0_u8; 2],
        comm,
    });
    entry.submit(0);
    Ok(())
}

#[tracepoint]
pub fn discoveryprobe_accept4(ctx: TracePointContext) -> u32 {
    // Passive: any read/reserve failure (or a failed accept) drops the event,
    // never disturbs the traced process.
    let _ = try_capture_accept(&ctx);
    0
}

fn try_capture_accept(ctx: &TracePointContext) -> Result<(), i64> {
    // `sys_exit_accept4`: a non-negative `ret` is the new connection fd, i.e. the
    // listening pid ACTUALLY took an inbound connection (a live server, not a
    // dormant bound socket). Gate on `ret >= 0` before doing any work; a negative
    // ret is an error and is dropped. Do the fallible read BEFORE reserving the
    // ring entry (reference-leak rule).
    // SAFETY: `read_at` reads a fixed-size field at a verifier-checked offset
    // within the tracepoint record the kernel itself populated; the offset is
    // within the record bounds for sys_exit_accept4.
    let ret = unsafe { ctx.read_at::<i64>(ACCEPT_RET_OFFSET)? };
    if ret < 0 {
        return Err(0);
    }
    let pid = (bpf_get_current_pid_tgid() >> 32) as u32;
    let comm = bpf_get_current_comm()?;

    let mut entry = ACCEPT_EVENTS.reserve::<AcceptEvent>(0).ok_or(0_i64)?;
    entry.write(AcceptEvent { pid, comm });
    entry.submit(0);
    Ok(())
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    // eBPF has no unwinding; a panic in a verified program is unreachable.
    loop {}
}
