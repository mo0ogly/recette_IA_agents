"""Relay a capture request to the privileged discoveryprobe broker.

The API is NON-privileged (design sec. 7): it never loads eBPF itself. It
connects to the broker's local socket -- the canonical Unix socket path, or a
loopback ``tcp:HOST:PORT`` endpoint on platforms without ``socket.AF_UNIX``
(Windows) -- sends ONE `capture` command line, reads the JSON response line,
and returns it. The broker holds CAP_BPF and does the work. If the socket is
unset or unreachable, the relay fails CLOSED (:class:`ProbeUnavailable`) -- it
never fabricates a capture (fail-safe).
"""

from __future__ import annotations

import json
import socket

from ..platform.probe.address import create_stream_socket, parse_probe_address


class ProbeUnavailable(RuntimeError):
    """The broker socket is not configured, not reachable, or returned garbage."""


def _connect(socket_path: str, timeout: float) -> socket.socket:
    """A connected stream socket for a unix-path or ``tcp:HOST:PORT`` address.

    Raises :class:`ProbeUnavailable` on any parse/connect failure (fail-safe)."""
    try:
        family, target = parse_probe_address(socket_path)
        sock = create_stream_socket(family)
    except (ValueError, OSError) as exc:
        raise ProbeUnavailable(f"broker socket {socket_path}: {exc}") from exc
    sock.settimeout(timeout)
    try:
        sock.connect(target if family == "tcp" else socket_path)  # type: ignore[arg-type]
    except OSError as exc:
        sock.close()
        raise ProbeUnavailable(f"broker socket {socket_path}: {exc}") from exc
    return sock


def open_watch(
    *, socket_path: str, agents: list[str], duration_ms: int, timeout: float = 2.0
) -> socket.socket:
    """Open a gap-free passive stream: connect, send ONE ``watch`` command, and
    return the connected socket the caller reads newline-delimited recording
    lines from (one per ``duration_ms`` slice) until it closes the socket.

    The broker keeps the eBPF probe attached for the connection's life, so no
    event is lost between slices (unlike repeated bounded captures). Raises
    :class:`ProbeUnavailable` on connect failure (fail-safe)."""
    request = json.dumps({"command": "watch", "agents": agents, "duration_ms": duration_ms})
    sock = _connect(socket_path, timeout)
    try:
        sock.sendall((request + "\n").encode("utf-8"))
    except OSError as exc:
        sock.close()
        raise ProbeUnavailable(f"broker socket {socket_path}: {exc}") from exc
    return sock


def relay_capture(
    *,
    socket_path: str,
    agents: list[str],
    duration_ms: int,
    agent_pids: dict[str, list[int]] | None = None,
    timeout: float = 30.0,
) -> dict:
    """Send one bounded capture command to the broker and return its JSON reply.

    ``agent_pids`` (optional) gives the broker exact pids per agent for PRECISE
    attribution -- the launcher passes the spawned child pid, so the match does
    not rely on the (15-byte truncated) ``comm``. Raises :class:`ProbeUnavailable`
    on any connect / timeout / protocol error so the caller fails closed rather
    than invent a result.
    """
    payload: dict = {"command": "capture", "agents": agents, "duration_ms": duration_ms}
    if agent_pids:
        payload["agent_pids"] = agent_pids
    request = json.dumps(payload)
    chunks: list[bytes] = []
    try:
        with _connect(socket_path, timeout) as sock:
            sock.sendall((request + "\n").encode("utf-8"))
            sock.shutdown(socket.SHUT_WR)
            while True:
                data = sock.recv(65536)
                if not data:
                    break
                chunks.append(data)
    except OSError as exc:
        raise ProbeUnavailable(f"broker socket {socket_path}: {exc}") from exc

    raw = b"".join(chunks).decode("utf-8").strip()
    if not raw:
        raise ProbeUnavailable(f"broker socket {socket_path}: empty response")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProbeUnavailable(f"broker returned non-JSON: {exc}") from exc
