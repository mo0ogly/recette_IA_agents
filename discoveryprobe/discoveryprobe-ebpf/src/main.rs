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
    maps::RingBuf,
    programs::TracePointContext,
};
use discoveryprobe_common::{ConnectEvent, DnsEvent, ExecEvent, FileEvent, ForkEvent, PATH_LEN, QNAME_LEN};

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

/// Maximum number of QNAME labels the bounded parse will walk. A constant so
/// the verifier sees a fixed loop bound; 8 labels covers realistic hostnames
/// (`a.b.c.d.e.f.g.h`), and a longer name is simply truncated (passive).
const MAX_LABELS: usize = 8;

/// Maximum bytes of a single DNS label per the RFC (a length byte is 6 bits of
/// length when the top two bits are 0). The parse bounds each label copy to
/// this AND to the remaining output buffer.
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
    // The agent's outbound TCP connect -- for an LLM agent, the HTTPS dial to
    // the provider. agentwatch sees this in-process at httpcore; here we see it
    // at the kernel, without the agent's cooperation (catches a hook-blind
    // ghost). Read the userspace `sockaddr` pointer from the tracepoint record,
    // then probe-read its sockaddr_in fields.
    // SAFETY: `read_at` reads a fixed-size pointer field at a verifier-checked
    // offset within the tracepoint record the kernel itself populated; the
    // offset is within the record bounds for sys_enter_connect.
    let uservaddr = unsafe { ctx.read_at::<*const u8>(USERVADDR_OFFSET)? };
    if uservaddr.is_null() {
        return Err(0);
    }
    // sockaddr_in layout: sin_family u16 @0, sin_port u16 (network order) @2,
    // sin_addr u32 (network order) @4.
    // SAFETY: `bpf_probe_read_user` is the kernel-sanctioned fallible read of
    // userspace memory from an eBPF program -- a bad/unmapped address returns
    // Err (propagated by `?`) instead of faulting, so dereferencing the user
    // `sockaddr` pointer is sound.
    let family = unsafe { bpf_probe_read_user::<u16>(uservaddr as *const u16)? };
    if family != AF_INET {
        // IPv4 only for now; other families are dropped (documented boundary).
        return Err(0);
    }
    // SAFETY: same as above -- a fallible userspace read at the sin_port (+2)
    // offset within the sockaddr_in; an out-of-bounds read returns Err.
    let port = unsafe { bpf_probe_read_user::<u16>(uservaddr.wrapping_add(2) as *const u16)? };
    // SAFETY: same as above -- a fallible userspace read at the sin_addr (+4)
    // offset within the sockaddr_in; an out-of-bounds read returns Err.
    let addr = unsafe { bpf_probe_read_user::<u32>(uservaddr.wrapping_add(4) as *const u32)? };

    let pid = (bpf_get_current_pid_tgid() >> 32) as u32;
    let comm = bpf_get_current_comm()?;

    let mut entry = CONNECT_EVENTS.reserve::<ConnectEvent>(0).ok_or(0_i64)?;
    // `to_ne_bytes` preserves the exact in-memory (network-order) bytes the
    // kernel read, so userspace parses octets in order and the port big-endian.
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

    // 3. Walk the length-prefixed labels into a dotted name, ALL bounds constant
    // so the verifier accepts every read offset and copy length. `out_len` and
    // every index are masked with `& (QNAME_LEN - 1)` (QNAME_LEN is a power of
    // two) so each write is provably inside `qname`. `payload_off` runs over the
    // payload starting at the header; it is bounded by `MAX_LABELS * (1 +
    // MAX_LABEL_LEN)` which is a small constant.
    let mut qname = [0u8; QNAME_LEN];
    let mut out_len: usize = 0;
    let mut payload_off: usize = DNS_HEADER_LEN;
    let mut parsed_any = false;

    for _ in 0..MAX_LABELS {
        // Read the label length byte at the running payload offset.
        // SAFETY: fallible userspace read; a bad address returns Err. The
        // offset is bounded by a small constant (MAX_LABELS * 64).
        let len_byte = unsafe { bpf_probe_read_user::<u8>(buff.wrapping_add(payload_off))? };
        let label_len = len_byte as usize;
        if label_len == 0 {
            // Root label: end of QNAME.
            break;
        }
        if label_len > MAX_LABEL_LEN {
            // Compression pointer (top bits set) or malformed length: stop.
            break;
        }
        if parsed_any {
            // Separator between labels. Mask the index to a constant bound.
            let idx = out_len & (QNAME_LEN - 1);
            qname[idx] = b'.';
            out_len += 1;
        }
        // Copy `label_len` bytes, but the loop trip count is a CONSTANT
        // (MAX_LABEL_LEN); inner steps past `label_len` are skipped, and every
        // write index is masked to a constant bound for the verifier.
        let mut i: usize = 0;
        while i < MAX_LABEL_LEN {
            if i >= label_len {
                break;
            }
            // Leave room for the trailing NUL: stop one short of the buffer.
            if out_len >= QNAME_LEN - 1 {
                break;
            }
            let src_off = payload_off + 1 + i;
            // SAFETY: fallible userspace read at a constant-bounded offset.
            let byte = unsafe { bpf_probe_read_user::<u8>(buff.wrapping_add(src_off))? };
            let idx = out_len & (QNAME_LEN - 1);
            qname[idx] = byte;
            out_len += 1;
            i += 1;
        }
        parsed_any = true;
        payload_off += 1 + label_len;
        if out_len >= QNAME_LEN - 1 {
            break;
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

#[cfg(not(test))]
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    // eBPF has no unwinding; a panic in a verified program is unreachable.
    loop {}
}
